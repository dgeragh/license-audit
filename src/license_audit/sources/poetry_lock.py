"""Parse dependencies from a poetry.lock file."""

from __future__ import annotations

import tomllib
from pathlib import Path

from license_audit.sources.base import PackageSpec
from license_audit.util import canonicalize

_SUPPORTED_LOCK_VERSIONS: tuple[str, ...] = ("1", "2")


class PoetryLockSource:
    """Parse a poetry.lock file to extract package specs.

    Poetry's lock file is already a flat transitive list -- every package
    needed for any group is a top-level ``[[package]]`` entry, with the
    ``groups`` field (lock 2.x) or ``category`` field (lock 1.x) indicating
    membership. No recursive walking is required.
    """

    def __init__(self, lock_path: Path, groups: list[str] | None = None) -> None:
        self._lock_path = lock_path
        self._groups = groups

    def parse(self) -> list[PackageSpec]:
        """Parse poetry.lock and return all dependency package specs."""
        if not self._lock_path.exists():
            msg = f"poetry.lock not found at {self._lock_path}"
            raise FileNotFoundError(msg)

        _reject_optional_selectors(self._groups)

        with open(self._lock_path, "rb") as f:
            data = tomllib.load(f)

        _validate_lock_version(data)

        packages = data.get("package", [])
        if not isinstance(packages, list):
            return []

        specs: list[PackageSpec] = []
        seen: set[str] = set()
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            spec = _build_spec(pkg, self._groups)
            if spec is None:
                continue
            if spec.name in seen:
                continue
            seen.add(spec.name)
            specs.append(spec)
        return specs


def _reject_optional_selectors(groups: list[str] | None) -> None:
    """Raise if any ``optional:*`` selector was passed.

    poetry.lock does not preserve the project-level extras-to-package mapping,
    so ``optional:<extra>`` cannot be honored from the lock file alone. Users
    who need extras filtering should target ``pyproject.toml`` instead.
    """
    if groups is None:
        return
    for selector in groups:
        if selector.startswith("optional:"):
            msg = (
                f"poetry.lock cannot honor the '{selector}' selector. "
                "Use pyproject.toml as the source for extras-based filtering."
            )
            raise ValueError(msg)


def _validate_lock_version(data: dict[str, object]) -> None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        msg = "poetry.lock missing [metadata] section"
        raise ValueError(msg)  # noqa: TRY004
    raw = metadata.get("lock-version")
    if not isinstance(raw, str):
        msg = f"Unsupported poetry.lock version: {raw!r}"
        raise ValueError(msg)  # noqa: TRY004
    major = raw.split(".", 1)[0]
    if major not in _SUPPORTED_LOCK_VERSIONS:
        msg = (
            f"Unsupported poetry.lock version: {raw} "
            f"(expected major version in {_SUPPORTED_LOCK_VERSIONS})"
        )
        raise ValueError(msg)


def _build_spec(
    pkg: dict[str, object],
    groups: list[str] | None,
) -> PackageSpec | None:
    """Convert one ``[[package]]`` entry into a PackageSpec, applying group filter."""
    raw_name = pkg.get("name")
    raw_version = pkg.get("version")
    if not isinstance(raw_name, str) or not isinstance(raw_version, str):
        return None
    if not raw_name or not raw_version:
        return None

    pkg_groups = _resolve_pkg_groups(pkg)
    if not _matches_selector(pkg_groups, groups):
        return None

    name = canonicalize(raw_name)
    source_url = _build_source_url(pkg.get("source"))
    return PackageSpec(
        name=name,
        version_constraint=f"=={raw_version}",
        source_url=source_url,
    )


def _resolve_pkg_groups(pkg: dict[str, object]) -> list[str]:
    """Return the list of groups a package belongs to.

    Lock 2.x has ``groups = [...]``. Lock 1.x has ``category = "main" | "dev"``.
    Default to ``["main"]`` when neither is present.
    """
    raw = pkg.get("groups")
    if isinstance(raw, list):
        return [str(g) for g in raw if isinstance(g, str)]
    category = pkg.get("category")
    if isinstance(category, str) and category:
        return [category]
    return ["main"]


def _matches_selector(pkg_groups: list[str], selectors: list[str] | None) -> bool:
    """Return True if the package's groups satisfy the user's selectors."""
    if selectors is None:
        return True
    for selector in selectors:
        if selector == "main" and "main" in pkg_groups:
            return True
        if selector == "dev" and "dev" in pkg_groups:
            return True
        if selector.startswith("group:"):
            group_name = selector[len("group:") :]
            if group_name in pkg_groups:
                return True
    return False


def _build_source_url(source: object) -> str:
    """Build a ``git+URL@ref`` string for git sources, or empty for others."""
    if not isinstance(source, dict):
        return ""
    if source.get("type") != "git":
        return ""
    url = source.get("url")
    if not isinstance(url, str) or not url:
        return ""
    ref = source.get("resolved_reference") or source.get("reference")
    if isinstance(ref, str) and ref:
        return f"git+{url}@{ref}"
    return f"git+{url}"
