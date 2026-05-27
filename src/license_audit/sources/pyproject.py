"""Parse dependencies from a pyproject.toml file."""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from license_audit.sources.base import PackageSpec
from license_audit.util import canonicalize


class PyprojectSource:
    """Parse all dependencies from a pyproject.toml to extract package specs.

    Covers:
    - ``[project.dependencies]``
    - ``[project.optional-dependencies.*]`` (extras)
    - ``[dependency-groups.*]`` (PEP 735)
    - ``[tool.uv.dev-dependencies]`` (uv-specific legacy)
    - ``[tool.poetry.dependencies]`` and ``[tool.poetry.group.<g>.dependencies]``
      when entries reference a custom source via ``source = "name"``.
    """

    def __init__(self, pyproject_path: Path, groups: list[str] | None = None) -> None:
        self._path = pyproject_path
        self._groups = groups

    def _include(self, selector: str) -> bool:
        """Return True if the given group selector should be included."""
        return self._groups is None or selector in self._groups

    def parse(self) -> list[PackageSpec]:
        """Parse pyproject.toml dependencies and return package specs."""
        if not self._path.exists():
            msg = f"pyproject.toml not found at {self._path}"
            raise FileNotFoundError(msg)

        with open(self._path, "rb") as f:
            data = tomllib.load(f)

        raw = self._collect_raw_deps(data)
        specs = _parse_requirements(raw)

        # Resolve index URLs from uv/poetry tool tables.
        uv_dep_index = _build_uv_dep_index(data)
        poetry_dep_index = _build_poetry_dep_index(data, self._include)
        specs = _apply_index_urls(specs, uv_dep_index, poetry_dep_index)

        # Merge in any poetry table-form deps that reference a custom source
        # and weren't already declared in PEP 621.
        seen = {s.name for s in specs}
        for extra in _collect_poetry_indexed_deps(
            data, poetry_dep_index, self._include
        ):
            if extra.name not in seen:
                specs.append(extra)
                seen.add(extra.name)

        return specs

    def _collect_raw_deps(self, data: dict[str, object]) -> list[str]:
        """Collect raw dependency strings from all selected groups."""
        raw: list[str] = []

        # [project.dependencies]
        if self._include("main"):
            project = data.get("project", {})
            raw.extend(
                _as_str_list(
                    project.get("dependencies") if isinstance(project, dict) else None
                )
            )

        # [project.optional-dependencies.*]
        project = data.get("project", {})
        opt_deps = (
            project.get("optional-dependencies", {})
            if isinstance(project, dict)
            else {}
        )
        if isinstance(opt_deps, dict):
            for name, group_deps in opt_deps.items():
                if self._include(f"optional:{name}"):
                    raw.extend(_as_str_list(group_deps))

        # [dependency-groups.*] (PEP 735)
        dep_groups = data.get("dependency-groups", {})
        if isinstance(dep_groups, dict):
            for name, group_deps in dep_groups.items():
                if self._include(f"group:{name}"):
                    raw.extend(_as_str_list(group_deps))

        # [tool.uv.dev-dependencies]
        if self._include("dev"):
            tool = data.get("tool", {})
            uv = tool.get("uv", {}) if isinstance(tool, dict) else {}
            uv_dev = uv.get("dev-dependencies") if isinstance(uv, dict) else None
            raw.extend(_as_str_list(uv_dev))

        return raw


def _parse_requirements(raw: list[str]) -> list[PackageSpec]:
    """Parse raw requirement strings into deduplicated PackageSpecs."""
    seen: set[str] = set()
    specs: list[PackageSpec] = []
    for dep_str in raw:
        try:
            req = Requirement(dep_str)
        except InvalidRequirement:
            continue

        name = canonicalize(req.name)
        if name in seen:
            continue
        seen.add(name)

        constraint = str(req.specifier) if req.specifier else ""
        source_url = req.url or ""
        extras = frozenset(req.extras) if req.extras else frozenset()
        specs.append(
            PackageSpec(
                name=name,
                version_constraint=constraint,
                source_url=source_url,
                extras=extras,
            )
        )
    return specs


def _as_str_list(value: object) -> list[str]:
    """Coerce a value to a list of strings, filtering out non-string items."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _build_uv_dep_index(data: dict[str, object]) -> dict[str, str]:
    """Map ``canonical_dep_name -> index_url`` from ``[tool.uv.sources]``."""
    tool = data.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    if not isinstance(uv, dict):
        return {}

    index_by_name = _uv_index_urls(uv.get("index"))
    sources = uv.get("sources")
    if not isinstance(sources, dict):
        return {}

    result: dict[str, str] = {}
    for dep_name, value in sources.items():
        if not isinstance(value, dict):
            continue
        idx_name = value.get("index")
        if not isinstance(idx_name, str):
            continue
        url = index_by_name.get(idx_name)
        if url:
            result[canonicalize(dep_name)] = url
    return result


def _uv_index_urls(indexes: object) -> dict[str, str]:
    """Map ``index_name -> url`` from ``[[tool.uv.index]]`` entries."""
    out: dict[str, str] = {}
    if not isinstance(indexes, list):
        return out
    for entry in indexes:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        url = entry.get("url")
        if isinstance(name, str) and isinstance(url, str) and name and url:
            out[name] = url
    return out


def _build_poetry_dep_index(
    data: dict[str, object],
    include: Callable[[str], bool],
) -> dict[str, str]:
    """Map ``canonical_dep_name -> index_url`` from poetry table-form deps."""
    poetry = _poetry_section(data)
    if poetry is None:
        return {}

    source_by_name = _poetry_source_urls(poetry)
    if not source_by_name:
        return {}

    result: dict[str, str] = {}
    for section in _selected_poetry_dep_sections(poetry, include):
        _scan_poetry_deps(section, source_by_name, result)
    return result


def _poetry_section(data: dict[str, object]) -> dict[str, object] | None:
    """Return the ``[tool.poetry]`` table or None."""
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    poetry = tool.get("poetry")
    if not isinstance(poetry, dict):
        return None
    return poetry


def _poetry_source_urls(poetry: dict[str, object]) -> dict[str, str]:
    """Map ``source_name -> url`` from ``[[tool.poetry.source]]`` entries."""
    sources = poetry.get("source")
    if not isinstance(sources, list):
        return {}
    out: dict[str, str] = {}
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        url = entry.get("url")
        if isinstance(name, str) and isinstance(url, str) and name and url:
            out[name] = url
    return out


def _scan_poetry_deps(
    deps: dict[str, object],
    source_by_name: dict[str, str],
    result: dict[str, str],
) -> None:
    """Populate ``result`` with deps that reference a named poetry source."""
    for dep_name, value in deps.items():
        if not isinstance(value, dict):
            continue
        src = value.get("source")
        if not isinstance(src, str):
            continue
        url = source_by_name.get(src)
        if url:
            result[canonicalize(dep_name)] = url


def _apply_index_urls(
    specs: list[PackageSpec],
    *index_maps: dict[str, str],
) -> list[PackageSpec]:
    """Return specs with ``index_url`` set from the first map that knows them."""
    out: list[PackageSpec] = []
    for spec in specs:
        if spec.index_url:
            out.append(spec)
            continue
        url = ""
        for mapping in index_maps:
            url = mapping.get(spec.name, "")
            if url:
                break
        if url:
            out.append(
                PackageSpec(
                    name=spec.name,
                    version_constraint=spec.version_constraint,
                    source_url=spec.source_url,
                    extras=spec.extras,
                    index_url=url,
                )
            )
        else:
            out.append(spec)
    return out


def _collect_poetry_indexed_deps(
    data: dict[str, object],
    poetry_dep_index: dict[str, str],
    include: Callable[[str], bool],
) -> list[PackageSpec]:
    """Build specs for poetry table-form deps that reference a custom source."""
    poetry = _poetry_section(data)
    if poetry is None or not poetry_dep_index:
        return []

    sections = _selected_poetry_dep_sections(poetry, include)
    out: list[PackageSpec] = []
    seen: set[str] = set()
    for section in sections:
        for dep_name, value in section.items():
            if not isinstance(value, dict):
                continue
            if not isinstance(value.get("source"), str):
                continue
            canonical = canonicalize(dep_name)
            if canonical in seen:
                continue
            index_url = poetry_dep_index.get(canonical)
            if not index_url:
                continue
            seen.add(canonical)
            out.append(
                PackageSpec(
                    name=canonical,
                    version_constraint=_poetry_version_constraint(value.get("version")),
                    index_url=index_url,
                )
            )
    return out


def _selected_poetry_dep_sections(
    poetry: dict[str, object],
    include: Callable[[str], bool],
) -> list[dict[str, object]]:
    """Return the poetry dep-table dicts the user's selectors include."""
    sections: list[dict[str, object]] = []
    if include("main"):
        main = poetry.get("dependencies")
        if isinstance(main, dict):
            sections.append(main)
    groups = poetry.get("group")
    if not isinstance(groups, dict):
        return sections
    for group_name, group_body in groups.items():
        if not _poetry_group_selected(group_name, include):
            continue
        if not isinstance(group_body, dict):
            continue
        deps = group_body.get("dependencies")
        if isinstance(deps, dict):
            sections.append(deps)
    return sections


def _poetry_group_selected(group_name: str, include: Callable[[str], bool]) -> bool:
    """Return True if a poetry group's selector tag should be included."""
    if group_name == "dev" and include("dev"):
        return True
    return include(f"group:{group_name}")


def _poetry_version_constraint(value: object) -> str:
    """Coerce a poetry dep version into a PEP 440 constraint, or empty."""
    if not isinstance(value, str) or not value.strip():
        return ""
    candidate = value.strip()
    # If the string has no operator, treat it as an exact pin.
    if candidate[0].isdigit():
        candidate = f"=={candidate}"
    try:
        SpecifierSet(candidate)
    except InvalidSpecifier:
        return ""
    return candidate
