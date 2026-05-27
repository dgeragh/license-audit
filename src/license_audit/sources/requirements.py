"""Parse dependencies from a requirements.txt file."""

from __future__ import annotations

from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from license_audit.sources.base import PackageSpec
from license_audit.util import canonicalize


class RequirementsSource:
    """Parse a requirements.txt file to extract package specs."""

    def __init__(
        self, requirements_path: Path, groups: list[str] | None = None
    ) -> None:
        self._path = requirements_path
        # groups is accepted for API consistency but ignored (flat format).

    def parse(self) -> list[PackageSpec]:
        """Parse requirements.txt and return package specs."""
        if not self._path.exists():
            msg = f"requirements.txt not found at {self._path}"
            raise FileNotFoundError(msg)

        lines = self._path.read_text(encoding="utf-8").splitlines()
        specs: list[PackageSpec] = []
        primary_url = ""  # from --index-url / -i
        extra_url = ""  # first --extra-index-url

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-"):
                flag, value = _parse_index_directive(line)
                if value:
                    if flag in ("-i", "--index-url") and not primary_url:
                        primary_url = value
                    elif flag == "--extra-index-url" and not extra_url:
                        extra_url = value
                continue
            try:
                req = Requirement(line)
            except InvalidRequirement:
                continue

            name = canonicalize(req.name)
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

        index_url = primary_url or extra_url
        if index_url:
            specs = [_with_index(s, index_url) for s in specs]
        return specs


def _parse_index_directive(line: str) -> tuple[str, str]:
    """Return ``(flag, url)`` for index-url directives, or ``("", "")`` otherwise."""
    parts = line.split(None, 1)
    flag = parts[0]
    value = parts[1].strip() if len(parts) == 2 else ""
    # Handle `--flag=URL` form when there's no whitespace-separated value.
    if not value and "=" in flag:
        flag, _, value = flag.partition("=")
        value = value.strip()
    if flag in ("-i", "--index-url", "--extra-index-url"):
        return flag, value
    return "", ""


def _with_index(spec: PackageSpec, index_url: str) -> PackageSpec:
    """Return a copy of ``spec`` with ``index_url`` populated."""
    return PackageSpec(
        name=spec.name,
        version_constraint=spec.version_constraint,
        source_url=spec.source_url,
        extras=spec.extras,
        index_url=index_url,
    )
