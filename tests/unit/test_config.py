"""Tests for configuration loading."""

from pathlib import Path

from license_audit.config import get_project_name, load_config


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
