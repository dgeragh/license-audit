"""Tests for configuration loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from license_audit.config import LicenseAuditConfig, get_project_name, load_config


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

    def test_unknown_key_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.license-audit]\nfail-on-unkown = false\n"
        )
        with pytest.raises(ValidationError, match="Extra inputs"):
            load_config(tmp_path)

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
        with pytest.raises(ValidationError, match="not a recognized SPDX"):
            load_config(tmp_path)


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
