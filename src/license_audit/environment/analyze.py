"""Analyze a Python environment for dependency licenses."""

from __future__ import annotations

from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

from license_audit.core.models import DependencyNode, PackageLicense
from license_audit.licenses.detection import detect_license
from license_audit.util import MetadataReader, canonicalize


def analyze_environment(
    project_name: str,
    reader: MetadataReader,
    overrides: dict[str, str] | None = None,
) -> DependencyNode:
    """Build the full dependency tree for `project_name`.

    Walks Requires-Dist from the root, then appends any leftover
    packages the reader can see (dev tools, docs deps, etc.) as direct
    dependencies of the root.
    """
    overrides = overrides or {}
    visited: set[str] = set()
    root = _resolve_package(project_name, reader, overrides, visited)

    for name in reader.iter_package_names():
        if name not in visited:
            node = _resolve_package(name, reader, overrides, visited)
            root.dependencies.append(node)

    return root


def _resolve_package(
    name: str,
    reader: MetadataReader,
    overrides: dict[str, str],
    visited: set[str],
    extras: frozenset[str] = frozenset(),
) -> DependencyNode:
    """Recursively resolve a package and its dependencies."""
    canonical = canonicalize(name)
    version = _get_version(canonical, reader)
    detected = detect_license(canonical, reader, overrides)

    pkg = PackageLicense(
        name=canonical,
        version=version,
        license_expression=detected.expression,
        declared_license=detected.declared_license,
        license_source=detected.source,
    )

    if canonical in visited:
        return DependencyNode(package=pkg)

    visited.add(canonical)
    deps: list[DependencyNode] = []

    for req_str in _get_requires_dist(canonical, reader):
        try:
            req = Requirement(req_str)
        except InvalidRequirement:
            continue

        # Drop deps whose markers don't apply here. Markers are evaluated
        # against each requested extra so optional deps gated by
        # ``extra == "..."`` come through.
        if req.marker and not _marker_matches(req.marker, extras):
            continue

        dep_extras = frozenset(req.extras) if req.extras else frozenset()
        dep_node = _resolve_package(req.name, reader, overrides, visited, dep_extras)
        deps.append(dep_node)

    return DependencyNode(package=pkg, dependencies=deps)


def _marker_matches(marker: Any, extras: frozenset[str]) -> bool:
    """True if `marker` evaluates true here, with or without an extra."""
    if marker.evaluate():
        return True
    return any(marker.evaluate({"extra": extra}) for extra in extras)


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
