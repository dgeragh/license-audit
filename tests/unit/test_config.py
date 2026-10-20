"""Tests for configuration loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from license_audit.config import (
    LicenseAuditConfig,
    get_project_dependencies,
    get_project_name,
    load_config,
)


class TestLoadConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)
        assert config.fail_on_unknown is True
        assert config.policy == "permissive"
        assert config.allowed_licenses == []
        assert config.denied_licenses == []
        assert config.overrides == {}

    def test_from_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.license-audit]\n"
            "fail-on-unknown = false\n"
            'policy = "strong-copyleft"\n'
            'allowed-licenses = ["MIT", "Apache-2.0"]\n'
            'denied-licenses = ["GPL-3.0-only"]\n'
            "\n"
            "[tool.license-audit.overrides]\n"
            'some-pkg = "MIT"\n'
        )
        config = load_config(tmp_path)
        assert config.fail_on_unknown is False
        assert config.policy == "strong-copyleft"
        assert config.allowed_licenses == ["MIT", "Apache-2.0"]
        assert config.denied_licenses == ["GPL-3.0-only"]
        assert config.overrides == {"some-pkg": "MIT"}

    def test_missing_section(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')
        config = load_config(tmp_path)
        assert config.fail_on_unknown is True

    def test_target_from_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.license-audit]\ntarget = "."\n')
        config = load_config(tmp_path)
        assert config.target == "."

    def test_target_default_is_none(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)
        assert config.target is None

    def test_license_classifications_from_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.license-audit.license-classifications]\n"
            '"Proprietary License" = "permissive"\n'
        )
        config = load_config(tmp_path)
        assert config.license_classifications == {"Proprietary License": "permissive"}

    def test_license_classifications_default_empty(self, tmp_path: Path) -> None:
        assert load_config(tmp_path).license_classifications == {}

    def test_malformed_toml_raises(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("this is = = not valid [[[\n")
        with pytest.raises(ValueError, match="Could not parse"):
            load_config(tmp_path)

    def test_unreadable_pyproject_raises(self, tmp_path: Path) -> None:
        # A directory exists but can't be opened as a file on any platform.
        (tmp_path / "pyproject.toml").mkdir()
        with pytest.raises(ValueError, match="Could not read"):
            load_config(tmp_path)

    def test_unknown_key_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.license-audit]\nfail-on-unkown = false\n"
        )
        with pytest.raises(ValueError, match="fail-on-unkown: unknown key"):
            load_config(tmp_path)

    def test_errors_read_as_pyproject_keys(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.license-audit]\n"
            'policy = "lenient"\n'
            'fail-on-unknown = "maybe"\n'
            'allowed-licenses = ["not a license"]\n'
        )
        with pytest.raises(ValueError) as caught:
            load_config(tmp_path)
        message = str(caught.value)
        assert message.splitlines()[0] == (
            "Invalid [tool.license-audit] configuration in "
            f"{tmp_path / 'pyproject.toml'}:"
        )
        assert "  policy: Input should be 'permissive'" in message
        assert "(got 'lenient')" in message
        assert "  fail-on-unknown: Input should be a valid boolean" in message
        assert "  allowed-licenses entry 'not a license' must be" in message
        assert "pydantic" not in message
        assert "LicenseAuditConfig" not in message

    def test_non_table_section_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[tool]\n"license-audit" = "oops"\n')
        with pytest.raises(ValueError, match="must be a table"):
            load_config(tmp_path)


class TestLicenseClassificationsValidation:
    def test_valid_category_accepted(self) -> None:
        config = LicenseAuditConfig(
            license_classifications={"Custom License": "weak-copyleft"}
        )
        assert config.license_classifications == {"Custom License": "weak-copyleft"}

    def test_invalid_category_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be one of"):
            LicenseAuditConfig(
                license_classifications={"Custom License": "super-permissive"}
            )

    def test_unknown_category_rejected(self) -> None:
        # Classifying *to* unknown is a no-op that would still fail policy.
        with pytest.raises(ValidationError, match="must be one of"):
            LicenseAuditConfig(license_classifications={"Custom License": "unknown"})

    def test_non_dict_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LicenseAuditConfig(
                license_classifications=["Custom License"]  # type: ignore[arg-type]
            )

    def test_non_string_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LicenseAuditConfig(
                license_classifications={"Custom License": 1}  # type: ignore[dict-item]
            )


class TestOverridesValidation:
    def test_valid_spdx_accepted(self) -> None:
        config = LicenseAuditConfig(overrides={"some-pkg": "MIT"})
        assert config.overrides == {"some-pkg": "MIT"}

    def test_alias_normalized(self) -> None:
        config = LicenseAuditConfig(overrides={"some-pkg": "apache"})
        assert config.overrides == {"some-pkg": "Apache-2.0"}

    def test_compound_expression_accepted(self) -> None:
        config = LicenseAuditConfig(overrides={"some-pkg": "Apache-2.0 OR MIT"})
        assert config.overrides == {"some-pkg": "Apache-2.0 OR MIT"}

    def test_unrecognized_value_rejected(self) -> None:
        with pytest.raises(ValidationError, match="not a recognized SPDX"):
            LicenseAuditConfig(overrides={"some-pkg": "Custom EULA"})

    def test_unrecognized_value_rejected_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.license-audit.overrides]\nsome-pkg = "Custom EULA"\n'
        )
        with pytest.raises(ValueError, match="not a recognized SPDX"):
            load_config(tmp_path)


class TestLicenseListValidation:
    def test_valid_entries_kept(self) -> None:
        config = LicenseAuditConfig(
            allowed_licenses=["MIT", "Apache-2.0"],
            denied_licenses=["GPL-3.0-only"],
        )
        assert config.allowed_licenses == ["MIT", "Apache-2.0"]
        assert config.denied_licenses == ["GPL-3.0-only"]

    def test_deprecated_id_normalized(self) -> None:
        """A deprecated id left as-is would never match a detected component
        (detection normalizes GPL-2.0 to GPL-2.0-only), making the denylist
        entry a silent no-op."""
        config = LicenseAuditConfig(denied_licenses=["GPL-2.0"])
        assert config.denied_licenses == ["GPL-2.0-only"]

    def test_alias_normalized(self) -> None:
        config = LicenseAuditConfig(allowed_licenses=["apache"])
        assert config.allowed_licenses == ["Apache-2.0"]

    def test_unrecognized_entry_rejected(self) -> None:
        with pytest.raises(ValidationError, match="single SPDX license"):
            LicenseAuditConfig(denied_licenses=["Custom EULA"])

    def test_compound_expression_rejected(self) -> None:
        """Matching is per component id, so an expression entry could never
        match anything."""
        with pytest.raises(ValidationError, match="single SPDX license"):
            LicenseAuditConfig(allowed_licenses=["MIT OR Apache-2.0"])

    def test_empty_group_rejected_cleanly(self) -> None:
        with pytest.raises(ValidationError, match="single SPDX license"):
            LicenseAuditConfig(denied_licenses=["()"])

    def test_normalized_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.license-audit]\ndenied-licenses = ["GPL-2.0"]\n'
        )
        config = load_config(tmp_path)
        assert config.denied_licenses == ["GPL-2.0-only"]

    def test_license_in_both_lists_rejected(self) -> None:
        with pytest.raises(ValidationError, match="both allowed-licenses and denied"):
            LicenseAuditConfig(allowed_licenses=["MIT"], denied_licenses=["mit"])

    def test_disjoint_lists_accepted(self) -> None:
        config = LicenseAuditConfig(
            allowed_licenses=["MIT"], denied_licenses=["GPL-2.0"]
        )
        assert config.denied_licenses == ["GPL-2.0-only"]


class TestGetProjectName:
    def test_reads_name(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "my-cool-project"\n')
        assert get_project_name(tmp_path) == "my-cool-project"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert get_project_name(tmp_path) == "unknown"

    def test_missing_project_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.other]\nfoo = 1\n")
        assert get_project_name(tmp_path) == "unknown"

    def test_malformed_toml_returns_unknown(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("this is = = not valid [[[\n")
        assert get_project_name(tmp_path) == "unknown"

    def test_unreadable_pyproject_returns_unknown(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").mkdir()
        assert get_project_name(tmp_path) == "unknown"


class TestGetProjectDependencies:
    def test_reads_every_declared_table(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            'name = "app"\n'
            'dependencies = ["requests>=2", "numpy; python_version >= \'3.11\'"]\n'
            "[project.optional-dependencies]\n"
            'fast = ["orjson"]\n'
            "[dependency-groups]\n"
            'dev = ["pytest>=9", {include-group = "lint"}]\n'
            'lint = ["ruff"]\n'
            "[tool.uv]\n"
            'dev-dependencies = ["mypy"]\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.11"\n'
            'click = "^8.2"\n'
            "[tool.poetry.group.docs.dependencies]\n"
            'mkdocs = "*"\n'
        )
        assert get_project_dependencies(tmp_path) == [
            "requests>=2",
            "numpy; python_version >= '3.11'",
            "orjson",
            "pytest>=9",
            "ruff",
            "mypy",
            "click",
            "mkdocs",
        ]

    def test_missing_or_malformed_pyproject_declares_nothing(
        self, tmp_path: Path
    ) -> None:
        assert get_project_dependencies(tmp_path) == []
        (tmp_path / "pyproject.toml").write_text("this is = = not valid [[[\n")
        assert get_project_dependencies(tmp_path) == []

    def test_wrongly_shaped_tables_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            'project = "oops"\n'
            "[dependency-groups]\n"
            'dev = "pytest"\n'
            "[tool.poetry]\n"
            'group = ["not", "a", "table"]\n'
        )
        assert get_project_dependencies(tmp_path) == []
