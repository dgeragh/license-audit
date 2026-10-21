"""Analyze a Python environment for dependency licenses."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from packaging.markers import UndefinedComparison
from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion

from license_audit.core.models import DependencyNode, PackageLicense
from license_audit.licenses.detection import detect_license
from license_audit.util import MetadataReader, canonicalize


def analyze_environment(
    project_name: str,
    reader: MetadataReader,
    overrides: dict[str, str] | None = None,
    declared: Iterable[str] = (),
) -> DependencyNode:
    """Build the full dependency tree for `project_name`.

    Walks Requires-Dist from the root, then adds the requirements `declared`
    in pyproject.toml that the root's metadata doesn't carry (dependency
    groups, extras, or everything when the project isn't installed) as direct
    dependencies. Any other installed package (dev tools, docs deps, etc.) is
    appended as direct too, those nothing else among them requires first, so
    a tool's own dependencies are attributed to the tool rather than to
    whichever package sorts first.
    """
    overrides = overrides or {}
    visited: dict[str, PackageLicense] = {}
    root = _resolve_package(project_name, reader, overrides, visited)
    direct = {node.package.name for node in root.dependencies}

    for req in _applicable(declared, reader):
        name = canonicalize(req.name)
        if name in direct or name == root.package.name:
            continue
        extras = frozenset(req.extras)
        root.dependencies.append(
            _resolve_package(req.name, reader, overrides, visited, extras)
        )
        direct.add(name)

    leftovers = [name for name in reader.iter_package_names() if name not in visited]
    required = {
        canonicalize(req.name)
        for name in leftovers
        for req in _applicable(_get_requires_dist(name, reader), reader)
    }
    for name in sorted(set(leftovers), key=lambda n: (n in required, n)):
        if name not in visited:
            root.dependencies.append(_resolve_package(name, reader, overrides, visited))

    return root


def missing_requirements(
    project_name: str,
    reader: MetadataReader,
    required: Iterable[str] = (),
) -> list[str]:
    """Names of the project's requirements that aren't installed.

    `required` are the requirements pyproject.toml makes unconditional; an
    installed project adds its own Requires-Dist. Those whose markers don't
    hold for the audited environment, and extras, are not required. A
    missing one means the environment isn't the project's, or is only
    partly provisioned, so its license went unchecked.
    """
    root = canonicalize(project_name)
    missing: set[str] = set()
    for req in _parsed([*required, *_get_requires_dist(root, reader)], reader):
        name = canonicalize(req.name)
        if name != root and not reader.is_installed(name):
            missing.add(name)
    return sorted(missing)


def _applicable(
    requirements: Iterable[str],
    reader: MetadataReader,
    extras: frozenset[str] = frozenset(),
) -> Iterator[Requirement]:
    """Parsed requirements whose markers hold here and that are installed.

    Markers are evaluated against each requested extra so optional deps
    gated by ``extra == "..."`` come through. A declared-but-absent
    requirement is skipped: auditing it would add a phantom node with an
    unknown license.
    """
    for req in _parsed(requirements, reader, extras):
        if reader.is_installed(req.name):
            yield req


def _parsed(
    requirements: Iterable[str],
    reader: MetadataReader,
    extras: frozenset[str] = frozenset(),
) -> Iterator[Requirement]:
    """Valid requirements whose markers hold for the audited environment."""
    for req_str in requirements:
        try:
            req = Requirement(req_str)
        except InvalidRequirement:
            continue
        if req.marker and not _marker_matches(
            req.marker, extras, reader.marker_environment
        ):
            continue
        yield req


def _resolve_package(
    name: str,
    reader: MetadataReader,
    overrides: dict[str, str],
    visited: dict[str, PackageLicense],
    extras: frozenset[str] = frozenset(),
) -> DependencyNode:
    """Recursively resolve a package and its dependencies."""
    canonical = canonicalize(name)
    seen = visited.get(canonical)
    if seen is not None:
        # Repeat edge: reuse the first visit's detection in a stub node.
        # A copy, because flatten() assigns parents on package objects.
        return DependencyNode(package=seen.model_copy())

    version = _get_version(canonical, reader)
    detected = detect_license(canonical, reader, overrides)

    pkg = PackageLicense(
        name=canonical,
        version=version,
        license_expression=detected.expression,
        declared_license=detected.declared_license,
        license_source=detected.source,
    )

    visited[canonical] = pkg
    deps = [
        _resolve_package(req.name, reader, overrides, visited, frozenset(req.extras))
        for req in _applicable(_get_requires_dist(canonical, reader), reader, extras)
    ]
    return DependencyNode(package=pkg, dependencies=deps)


def _marker_matches(
    marker: Any,
    extras: frozenset[str],
    environment: Mapping[str, str] | None = None,
) -> bool:
    """True if `marker` evaluates true here, with or without an extra.

    `environment` overrides marker values of the running interpreter, such
    as the audited virtualenv's Python version.
    """
    # The baseline evaluation supplies an empty `extra`: packaging releases
    # before ~24.3 raise UndefinedEnvironmentName on a bare evaluate() of
    # any marker referencing `extra`, and newer ones treat it as False
    # anyway.
    environment = environment or {}
    if _evaluate(marker, "", environment):
        return True
    return any(_evaluate(marker, extra, environment) for extra in extras)


def _evaluate(marker: Any, extra: str, environment: Mapping[str, str]) -> bool:
    # Before packaging 26, comparing platform_release against a Linux kernel
    # string ("6.5.0-14-generic") raised instead of evaluating false.
    try:
        return bool(marker.evaluate({**environment, "extra": extra}))
    except (InvalidVersion, UndefinedComparison):
        return False


def _get_version(package_name: str, reader: MetadataReader) -> str:
    meta = reader.read_metadata(package_name)
    if meta is not None:
        version = meta.get("Version")
        if version:
            return str(version)
    return "unknown"


def _get_requires_dist(package_name: str, reader: MetadataReader) -> list[str]:
    meta = reader.read_metadata(package_name)
    if meta is None:
        return []
    return meta.get_all("Requires-Dist") or []
