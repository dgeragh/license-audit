"""Load the [tool.license-audit] section from pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

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

    @field_validator("allowed_licenses", "denied_licenses", mode="after")
    @classmethod
    def _validate_license_lists(
        cls, value: list[str], info: ValidationInfo
    ) -> list[str]:
        # Entries are matched against detected components in canonical SPDX
        # form, so an alias or deprecated id ("GPL-2.0", "gpl") left as-is
        # would silently never match. Normalize here; reject what can't be.
        if not value:
            return value
        field = str(info.field_name).replace("_", "-")
        normalizer = SpdxNormalizer()
        normalized: list[str] = []
        for entry in value:
            spdx = normalizer.normalize(entry)
            if spdx == UNKNOWN_LICENSE or " AND " in spdx or " OR " in spdx:
                msg = (
                    f"{field} entry '{entry}' must be a single SPDX license "
                    f"identifier (e.g. 'MIT', 'GPL-3.0-only')."
                )
                raise ValueError(msg)
            normalized.append(spdx)
        return normalized

    @model_validator(mode="after")
    def _reject_overlapping_lists(self) -> Self:
        # The policy check and the action items would otherwise disagree on
        # a license that is both allowed and denied.
        overlap = sorted(set(self.allowed_licenses) & set(self.denied_licenses))
        if overlap:
            msg = (
                f"{', '.join(overlap)} cannot be in both allowed-licenses and "
                f"denied-licenses"
            )
            raise ValueError(msg)
        return self

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
    except OSError as exc:
        msg = f"Could not read {pyproject_path}: {exc}"
        raise ValueError(msg) from exc
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

    try:
        return LicenseAuditConfig.model_validate(normalized)
    except ValidationError as exc:
        raise ValueError(_describe_errors(exc, pyproject_path)) from exc


def _describe_errors(exc: ValidationError, path: Path) -> str:
    """Summarize `exc` for the user, naming keys as pyproject.toml spells them."""
    lines = [f"Invalid [tool.license-audit] configuration in {path}:"]
    for error in exc.errors():
        location = _toml_location(error["loc"])
        if error["type"] == "extra_forbidden":
            keys = sorted(f.replace("_", "-") for f in LicenseAuditConfig.model_fields)
            lines.append(
                f"  {location}: unknown key; expected one of {', '.join(keys)}"
            )
        elif error["type"] == "value_error" or not location:
            # Our own validators name the key and the offending value.
            lines.append(f"  {error['msg'].removeprefix('Value error, ')}")
        else:
            lines.append(f"  {location}: {error['msg']} (got {error['input']!r})")
    return "\n".join(lines)


def _toml_location(loc: tuple[int | str, ...]) -> str:
    """`allowed_licenses, 0` as `allowed-licenses[0]`, and so on."""
    if not loc:
        return ""
    head, *rest = loc
    return str(head).replace("_", "-") + "".join(
        f"[{part}]" if isinstance(part, int) else f"['{part}']" for part in rest
    )


def get_project_name(config_dir: Path | None = None) -> str:
    """Read [project].name from pyproject.toml, or 'unknown' if missing."""
    project = _table(_read_pyproject(config_dir).get("project"))
    return str(project.get("name", "unknown"))


def get_project_dependencies(config_dir: Path | None = None) -> list[str]:
    """Requirements pyproject.toml declares for the project.

    Covers [project] dependencies and optional-dependencies, PEP 735
    dependency groups, and the dev tables of uv and Poetry (Poetry entries
    by name). A virtual project, uv's default for applications, isn't
    installed into its own environment, so these are the only record of
    what it depends on directly.
    """
    data = _read_pyproject(config_dir)
    project = _table(data.get("project"))
    tool = _table(data.get("tool"))
    poetry = _table(tool.get("poetry"))
    lists = [
        project.get("dependencies"),
        *_table(project.get("optional-dependencies")).values(),
        *_table(data.get("dependency-groups")).values(),
        _table(tool.get("uv")).get("dev-dependencies"),
    ]
    poetry_tables = [
        poetry.get("dependencies"),
        poetry.get("dev-dependencies"),
        *(
            _table(group).get("dependencies")
            for group in _table(poetry.get("group")).values()
        ),
    ]
    # A dependency group may also hold {include-group = "..."} tables; every
    # group is read anyway, so only the requirement strings matter.
    requirements = [
        entry
        for entries in lists
        if isinstance(entries, list)
        for entry in entries
        if isinstance(entry, str)
    ]
    requirements += [
        name for table in poetry_tables for name in _table(table) if name != "python"
    ]
    return requirements


def _read_pyproject(config_dir: Path | None) -> dict[str, Any]:
    """Parsed pyproject.toml in `config_dir`, or {} if absent or unreadable."""
    pyproject_path = (config_dir or Path.cwd()) / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
