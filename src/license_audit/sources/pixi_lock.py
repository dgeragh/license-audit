"""Parse dependencies from a pixi.lock file."""

from __future__ import annotations

import platform
import sys
import warnings
from pathlib import Path

import yaml

from license_audit.sources.base import PackageSpec
from license_audit.util import canonicalize

_SUPPORTED_LOCK_VERSIONS: frozenset[int] = frozenset({5, 6})
_NOARCH = "noarch"


class PixiLockSource:
    """Parse a pixi.lock file to extract PyPI package specs.

    pixi.lock can contain both ``conda`` and ``pypi`` package entries. The
    license-audit pipeline provisions packages via ``uv pip install``, which
    cannot install conda packages, so conda entries are skipped with a
    warning. License coverage for conda packages is a documented follow-up.

    Environment selectors map as: ``main`` -> ``default`` env, ``dev`` ->
    ``dev`` env (when present), ``group:<name>`` -> env named ``<name>``.
    """

    def __init__(self, lock_path: Path, groups: list[str] | None = None) -> None:
        self._lock_path = lock_path
        self._groups = groups

    def parse(self) -> list[PackageSpec]:
        """Parse pixi.lock and return PyPI package specs for the host platform."""
        if not self._lock_path.exists():
            msg = f"pixi.lock not found at {self._lock_path}"
            raise FileNotFoundError(msg)

        _reject_optional_selectors(self._groups)

        with open(self._lock_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            msg = "pixi.lock did not contain a YAML mapping"
            raise ValueError(msg)  # noqa: TRY004

        _validate_lock_version(data)

        platform_key = _pixi_platform_key()
        environments = _coerce_dict(data.get("environments"))
        selected_envs = _select_environments(environments, self._groups)
        selected_pypi_urls, conda_count = _collect_env_refs(
            environments, selected_envs, platform_key
        )

        specs = _collect_pypi_specs(data.get("packages"), selected_pypi_urls)

        if conda_count:
            warnings.warn(
                f"Skipped {conda_count} conda package(s) from pixi.lock; "
                "only PyPI packages are audited",
                UserWarning,
                stacklevel=2,
            )

        return specs


def _reject_optional_selectors(groups: list[str] | None) -> None:
    """Raise if any ``optional:*`` selector was passed.

    pixi has no extras concept; environments serve as groups. Reject the
    selector outright rather than silently ignoring it.
    """
    if groups is None:
        return
    for selector in groups:
        if selector.startswith("optional:"):
            msg = (
                f"pixi.lock cannot honor the '{selector}' selector. "
                "pixi uses environments instead of extras; use "
                f"'group:<env_name>' or 'main' instead."
            )
            raise ValueError(msg)


def _validate_lock_version(data: dict[str, object]) -> None:
    raw = data.get("version")
    if not isinstance(raw, int) or raw not in _SUPPORTED_LOCK_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(_SUPPORTED_LOCK_VERSIONS))
        msg = f"Unsupported pixi.lock version: {raw!r} (expected one of {supported})"
        raise ValueError(msg)


def _pixi_platform_key() -> str:
    """Return the pixi platform token for the running host.

    Mirrors uv.lock's environment-marker filtering: only the host platform's
    packages are emitted, so the audit reflects what would actually install.
    """
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine == "arm64":
            return "osx-arm64"
        if machine in {"x86_64", "amd64"}:
            return "osx-64"
    elif sys.platform == "linux":
        if machine in {"x86_64", "amd64"}:
            return "linux-64"
        if machine in {"aarch64", "arm64"}:
            return "linux-aarch64"
    elif sys.platform.startswith("win"):
        if machine in {"x86_64", "amd64"}:
            return "win-64"
    msg = (
        f"Unsupported host platform for pixi.lock: "
        f"sys.platform={sys.platform!r}, machine={machine!r}"
    )
    raise ValueError(msg)


def _collect_env_refs(
    environments: dict[str, object],
    selected_envs: list[str],
    platform_key: str,
) -> tuple[set[str], int]:
    """Walk selected environments and collect pypi URLs + skipped conda count."""
    selected_pypi_urls: set[str] = set()
    conda_count = 0
    for env_name in selected_envs:
        env = _coerce_dict(environments.get(env_name))
        env_packages = _coerce_dict(env.get("packages"))
        for plat in (platform_key, _NOARCH):
            entries = env_packages.get(plat)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if "pypi" in entry:
                    url = entry.get("pypi")
                    if isinstance(url, str):
                        selected_pypi_urls.add(url)
                elif "conda" in entry:
                    conda_count += 1
    return selected_pypi_urls, conda_count


def _select_environments(
    environments: dict[str, object],
    groups: list[str] | None,
) -> list[str]:
    """Resolve which environment names to read based on user selectors."""
    if groups is None:
        return list(environments.keys())

    selected: list[str] = []
    for selector in groups:
        if selector == "main" and "default" in environments:
            selected.append("default")
        elif selector == "dev" and "dev" in environments:
            selected.append("dev")
        elif selector.startswith("group:"):
            env_name = selector[len("group:") :]
            if env_name in environments:
                selected.append(env_name)
    # Preserve order while deduping.
    seen: set[str] = set()
    ordered: list[str] = []
    for env in selected:
        if env not in seen:
            seen.add(env)
            ordered.append(env)
    return ordered


def _collect_pypi_specs(
    packages: object,
    selected_urls: set[str],
) -> list[PackageSpec]:
    """Walk the top-level ``packages`` list, returning matching PyPI entries.

    Handles both pixi lock-format shapes:
      - v6: ``- pypi: <url>`` (the value of ``pypi`` is the URL)
      - v5: ``- kind: pypi`` with a separate ``url`` field
    """
    if not isinstance(packages, list):
        return []

    specs: list[PackageSpec] = []
    seen_names: set[str] = set()
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        url = _entry_pypi_url(entry)
        if url is None:
            continue
        if url not in selected_urls:
            continue
        raw_name = entry.get("name")
        raw_version = entry.get("version")
        if not isinstance(raw_name, str) or not isinstance(raw_version, str):
            continue
        if not raw_name or not raw_version:
            continue
        canonical = canonicalize(raw_name)
        if canonical in seen_names:
            continue
        seen_names.add(canonical)
        specs.append(
            PackageSpec(
                name=canonical,
                version_constraint=f"=={raw_version}",
            )
        )
    return specs


def _entry_pypi_url(entry: dict[str, object]) -> str | None:
    """Return the PyPI URL of a top-level packages entry, or None if not pypi."""
    url = entry.get("pypi")
    if isinstance(url, str):
        return url
    if entry.get("kind") == "pypi":
        url = entry.get("url")
        if isinstance(url, str):
            return url
    return None


def _coerce_dict(value: object) -> dict[str, object]:
    """Return value if it's a dict; otherwise an empty dict."""
    if isinstance(value, dict):
        return value
    return {}
