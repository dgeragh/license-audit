"""Configuration management for license_audit.

Reads [tool.license-audit] from pyproject.toml.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from license_audit.core.models import PolicyLevel


class GroupSpec:
    """Valid dependency-group selectors for ``[tool.license-audit]``.

    A group entry is either a literal (``main``, ``dev``) or a prefixed
    name (``optional:<name>``, ``group:<name>``).
    """

    PREFIXES: tuple[str, ...] = ("optional:", "group:")
    LITERALS: tuple[str, ...] = ("main", "dev")

    @classmethod
    def validate(cls, entry: str) -> None:
        """Raise ``ValueError`` if ``entry`` is not a valid group selector."""
        if entry in cls.LITERALS:
            return
        for prefix in cls.PREFIXES:
            if entry.startswith(prefix):
                if not entry[len(prefix) :]:
                    msg = (
                        f"Invalid dependency group: '{entry}' "
                        f"(missing name after prefix)"
                    )
                    raise ValueError(msg)
                return
        msg = (
            f"Invalid dependency group: '{entry}'. "
            f"Must be 'main', 'dev', 'optional:<name>', or 'group:<name>'."
        )
        raise ValueError(msg)

    @classmethod
    def validate_list(cls, entries: list[str]) -> list[str]:
        """Validate every entry in ``entries``; return the list unchanged."""
        for entry in entries:
            cls.validate(entry)
        return entries


class LicenseAuditConfig(BaseModel):
    """Configuration from [tool.license-audit] in pyproject.toml."""

    fail_on_unknown: bool = True
    policy: PolicyLevel = PolicyLevel.PERMISSIVE
    allowed_licenses: list[str] = Field(default_factory=list)
    denied_licenses: list[str] = Field(default_factory=list)
    overrides: dict[str, str] = Field(default_factory=dict)
    dependency_groups: list[str] | None = None

    @field_validator("dependency_groups", mode="before")
    @classmethod
    def _validate_dependency_groups(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            msg = "dependency_groups must be a list of strings"
            raise TypeError(msg)
        return GroupSpec.validate_list(value)


def load_config(config_dir: Path | None = None) -> LicenseAuditConfig:
    """Load configuration from pyproject.toml in the given directory.

    Falls back to defaults if no config section is found.
    """
    if config_dir is None:
        config_dir = Path.cwd()

    pyproject_path = config_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return LicenseAuditConfig()

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    tool_config = data.get("tool", {}).get("license-audit", {})
    if not tool_config:
        return LicenseAuditConfig()

    # Normalize kebab-case keys to snake_case
    normalized: dict[str, object] = {}
    for key, value in tool_config.items():
        normalized[key.replace("-", "_")] = value

    return LicenseAuditConfig.model_validate(normalized)


def get_project_name(config_dir: Path | None = None) -> str:
    """Read the project name from pyproject.toml."""
    if config_dir is None:
        config_dir = Path.cwd()

    pyproject_path = config_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return "unknown"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    return str(data.get("project", {}).get("name", "unknown"))
