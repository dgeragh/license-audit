"""Parse dependencies from a uv.lock file."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.markers import Marker, UndefinedEnvironmentName

from license_audit.sources.base import PackageSpec
from license_audit.util import canonicalize


class UvLockSource:
    """Parse a uv.lock file to extract package specs."""

    def __init__(self, lock_path: Path, groups: list[str] | None = None) -> None:
        self._lock_path = lock_path
        self._groups = groups

    def parse(self) -> list[PackageSpec]:
        """Parse uv.lock and return all dependency package specs."""
        if not self._lock_path.exists():
            msg = f"uv.lock not found at {self._lock_path}"
            raise FileNotFoundError(msg)

        with open(self._lock_path, "rb") as f:
            data = tomllib.load(f)

        version = data.get("version")
        if version != 1:
            msg = f"Unsupported uv.lock version: {version} (expected 1)"
            raise ValueError(msg)

        packages = data.get("package", [])

        # Build lookup for dependency walking
        pkg_lookup: dict[str, dict[str, object]] = {}
        for pkg in packages:
            name = canonicalize(str(pkg.get("name", "")))
            pkg_lookup[name] = pkg

        # Find the root project (the one without a source registry)
        root_name = _find_root_package(packages)

        # Walk dependencies from the root
        visited: set[str] = set()
        specs: list[PackageSpec] = []
        _collect_deps(root_name, pkg_lookup, visited, specs, groups=self._groups)

        return specs


def _find_root_package(packages: list[dict[str, object]]) -> str:
    """Find the root project package in uv.lock (the one with editable or virtual source)."""
    for pkg in packages:
        source = pkg.get("source")
        if isinstance(source, dict) and (
            source.get("editable") or source.get("virtual")
        ):
            return canonicalize(str(pkg.get("name", "")))
    # Fallback: first package
    if packages:
        return canonicalize(str(packages[0].get("name", "")))
    return ""


def _include_group(groups: list[str] | None, selector: str) -> bool:
    """Return True if the given group selector should be included."""
    return groups is None or selector in groups


def _collect_deps(
    name: str,
    lookup: dict[str, dict[str, object]],
    visited: set[str],
    specs: list[PackageSpec],
    extras: set[str] | None = None,
    *,
    groups: list[str] | None = None,
    is_root: bool = True,
) -> None:
    """Recursively collect dependency specs from the lock file.

    Group filtering only applies at the root package level. Transitive
    dependencies of included groups are always followed.
    """
    if name in visited:
        return
    visited.add(name)

    pkg_entry = lookup.get(name, {})
    version = str(pkg_entry.get("version", ""))

    # Add this package if it has a version and is installable.
    if version:
        source = pkg_entry.get("source")
        if _is_registry_source(pkg_entry):
            specs.append(
                PackageSpec(
                    name=name,
                    version_constraint=f"=={version}",
                    index_url=_registry_url(pkg_entry),
                )
            )
        elif isinstance(source, dict) and "git" in source:
            specs.append(
                PackageSpec(
                    name=name,
                    version_constraint=f"=={version}",
                    source_url=_build_git_url(source),
                )
            )

    # Walk regular dependencies (root: only if "main" selected)
    if not is_root or _include_group(groups, "main"):
        _walk_dep_list(pkg_entry.get("dependencies", []), lookup, visited, specs)

    # Walk optional-dependencies for any requested extras
    _walk_extras(pkg_entry, extras, lookup, visited, specs)

    # Walk dev-dependencies (only present on the root package)
    if is_root:
        _walk_dev_deps(pkg_entry, groups, lookup, visited, specs)


def _walk_extras(
    pkg_entry: dict[str, object],
    extras: set[str] | None,
    lookup: dict[str, dict[str, object]],
    visited: set[str],
    specs: list[PackageSpec],
) -> None:
    """Walk optional-dependencies for any requested extras."""
    if not extras:
        return
    opt_deps = pkg_entry.get("optional-dependencies")
    if not isinstance(opt_deps, dict):
        return
    for extra in extras:
        group = opt_deps.get(extra, [])
        if isinstance(group, list):
            _walk_dep_list(group, lookup, visited, specs)


def _walk_dev_deps(
    pkg_entry: dict[str, object],
    groups: list[str] | None,
    lookup: dict[str, dict[str, object]],
    visited: set[str],
    specs: list[PackageSpec],
) -> None:
    """Walk dev-dependencies, filtering by group selectors."""
    dev_deps = pkg_entry.get("dev-dependencies")
    if not isinstance(dev_deps, dict):
        return
    for group_name, group_deps in dev_deps.items():
        # "dev" selector matches the "dev" group name;
        # "group:<name>" matches any dev-dependency group
        if not _include_group(groups, f"group:{group_name}") and not (
            group_name == "dev" and _include_group(groups, "dev")
        ):
            continue
        if isinstance(group_deps, list):
            _walk_dep_list(group_deps, lookup, visited, specs)


def _walk_dep_list(
    deps: object,
    lookup: dict[str, dict[str, object]],
    visited: set[str],
    specs: list[PackageSpec],
) -> None:
    """Walk a list of dependency entries, recursing into each."""
    if not isinstance(deps, list):
        return
    for dep_entry in deps:
        if not isinstance(dep_entry, dict):
            continue
        if not _marker_applies(dep_entry.get("marker")):
            continue
        dep_name = canonicalize(str(dep_entry.get("name", "")))
        dep_extras = _get_extras(dep_entry)
        if dep_name:
            _collect_deps(dep_name, lookup, visited, specs, dep_extras, is_root=False)


def _is_registry_source(pkg_entry: dict[str, object]) -> bool:
    """Return True if the package was resolved from a registry (e.g. PyPI)."""
    source = pkg_entry.get("source")
    if not isinstance(source, dict):
        return True  # no source info -- assume registry
    return "registry" in source


def _registry_url(pkg_entry: dict[str, object]) -> str:
    """Return the registry URL for a registry-sourced package, or empty string."""
    source = pkg_entry.get("source")
    if not isinstance(source, dict):
        return ""
    url = source.get("registry")
    if isinstance(url, str):
        return url
    return ""


def _build_git_url(source: dict[str, object]) -> str:
    """Build a pip-installable ``git+URL@ref`` string from a uv.lock git source."""
    url = str(source.get("git", ""))
    # Prefer exact commit, fall back to tag, then branch
    ref = source.get("rev") or source.get("tag") or source.get("branch")
    if ref:
        return f"git+{url}@{ref}"
    return f"git+{url}"


def _get_extras(dep_entry: dict[str, object]) -> set[str] | None:
    """Extract the set of extras from a dependency entry, if any."""
    extra = dep_entry.get("extra")
    if isinstance(extra, str) and extra:
        return {extra}
    if isinstance(extra, list) and extra:
        return {str(e) for e in extra}
    return None


def _marker_applies(marker_str: object) -> bool:
    """Evaluate whether a dependency marker matches the current environment."""
    if marker_str is None:
        return True
    if not isinstance(marker_str, str) or not marker_str.strip():
        return True
    try:
        return bool(Marker(marker_str).evaluate())
    except (UndefinedEnvironmentName, ValueError):
        return True
