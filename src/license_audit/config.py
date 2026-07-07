"""Load the [tool.license-audit] section from pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from license_audit.core.models import UNKNOWN_LICENSE, LicenseCategory, PolicyLevel
from license_audit.licenses.spdx import SpdxNormalizer


class LicenseAuditConfig(BaseModel):
    """Parsed [tool.license-audit] section."""

    model_config = ConfigDict(extra="forbid")

    fail_on_unknown: bool = True
    policy: PolicyLevel = PolicyLevel.PERMISSIVE
    allowed_licenses: list[str] = Field(default_factory=list)
    denied_licenses: list[str] = Field(default_factory=list)
    overrides: dict[str, str] = Field(default_factory=dict)
    ignored_packages: dict[str, str] = Field(default_factory=dict)
    license_classifications: dict[str, str] = Field(default_factory=dict)
    target: str | None = None

    @field_validator("ignored_packages", mode="before")
    @classmethod
    def _validate_ignored_packages(
        cls,
        value: object,
    ) -> dict[str, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            # Pydantic v2 wraps ValueError into ValidationError but passes
            # TypeError through as-is, so we raise ValueError for consistent
            # error surfacing even though TypeError would be more idiomatic.
            msg = "ignored-packages must be a table mapping package name to reason"
            raise ValueError(msg)  # noqa: TRY004
        for key, reason in value.items():
            if not isinstance(reason, str) or not reason.strip():
                msg = (
                    f"ignored-packages['{key}'] must be a non-empty string "
                    f"explaining why the package is ignored"
                )
                raise ValueError(msg)
        return value

    @field_validator("license_classifications", mode="before")
    @classmethod
    def _validate_license_classifications(
        cls,
        value: object,
    ) -> dict[str, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            msg = (
                "license-classifications must be a table mapping a license "
                "string to a category"
            )
            raise ValueError(msg)  # noqa: TRY004
        # "unknown" is excluded: the whole point is to *resolve* an unknown,
        # so re-asserting unknown would be a no-op that still fails policy.
        valid = sorted(
            c.value for c in LicenseCategory if c is not LicenseCategory.UNKNOWN
        )
        for key, category in value.items():
            if not isinstance(category, str) or category not in valid:
                msg = (
                    f"license-classifications['{key}'] must be one of: "
                    f"{', '.join(valid)}"
                )
                raise ValueError(msg)
        return value

    @field_validator("overrides", mode="after")
    @classmethod
    def _validate_overrides(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            return value
        normalizer = SpdxNormalizer()
        normalized: dict[str, str] = {}
        for key, expression in value.items():
            spdx = normalizer.normalize(expression)
            if spdx == UNKNOWN_LICENSE:
                msg = (
                    f"overrides['{key}'] value '{expression}' is not a "
                    f"recognized SPDX license expression (e.g. 'MIT', "
                    f"'Apache-2.0 OR MIT'). To record a judgement about a "
                    f"non-SPDX license, use "
                    f"[tool.license-audit.license-classifications] instead."
                )
                raise ValueError(msg)
            normalized[key] = spdx
        return normalized


def load_config(config_dir: Path | None = None) -> LicenseAuditConfig:
    """Load config from pyproject.toml, or return defaults if none found."""
    if config_dir is None:
        config_dir = Path.cwd()

    pyproject_path = config_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return LicenseAuditConfig()

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Could not parse {pyproject_path}: {exc}"
        raise ValueError(msg) from exc

    tool_config = data.get("tool", {}).get("license-audit", {})
    if not isinstance(tool_config, dict):
        msg = "[tool.license-audit] must be a table"
        raise ValueError(msg)  # noqa: TRY004
    if not tool_config:
        return LicenseAuditConfig()

    # pyproject convention is kebab-case; Pydantic fields are snake_case.
    normalized: dict[str, object] = {}
    for key, value in tool_config.items():
        normalized[key.replace("-", "_")] = value

    return LicenseAuditConfig.model_validate(normalized)


def get_project_name(config_dir: Path | None = None) -> str:
    """Read [project].name from pyproject.toml, or 'unknown' if missing."""
    if config_dir is None:
        config_dir = Path.cwd()

    pyproject_path = config_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return "unknown"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    return str(data.get("project", {}).get("name", "unknown"))
