"""Tests for the CLI group's exit-code handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click
from click.testing import CliRunner

from license_audit.cli.main import cli
from license_audit.core.models import AnalysisReport


class TestUsageErrorsExitOne:
    """Click's usage-error code is 2, which `check` reserves for unknowns."""

    def test_missing_target_path(self) -> None:
        result = CliRunner().invoke(cli, ["--target", "/nonexistent", "check"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_unknown_option(self) -> None:
        result = CliRunner().invoke(cli, ["check", "--bogus"])
        assert result.exit_code == 1
        assert "No such option" in result.output

    def test_invalid_policy(self) -> None:
        result = CliRunner().invoke(cli, ["--policy", "yolo", "check"])
        assert result.exit_code == 1

    def test_no_subcommand(self) -> None:
        result = CliRunner().invoke(cli, [])
        assert result.exit_code == 1
        assert "Usage:" in result.output


class TestConfigOption:
    """--config must name a pyproject.toml, not fall back to a sibling or defaults."""

    def test_file_with_another_name_rejected(self, tmp_path: Path) -> None:
        other = tmp_path / "audit.toml"
        other.write_text('[tool.license-audit]\npolicy = "strong-copyleft"\n')
        result = CliRunner().invoke(cli, ["--config", str(other), "check"])
        assert result.exit_code == 1
        assert "pyproject.toml" in result.output

    def test_directory_without_pyproject_rejected(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(cli, ["--config", str(tmp_path), "check"])
        assert result.exit_code == 1
        assert "no pyproject.toml" in result.output

    def test_pyproject_file_accepted(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\n')
        with patch(
            "license_audit.cli.check.run_audit", return_value=AnalysisReport()
        ) as run:
            result = CliRunner().invoke(cli, ["--config", str(pyproject), "check"])
        assert result.exit_code == 0
        assert run.call_args.args[2] == tmp_path

    def test_directory_with_pyproject_accepted(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        with patch(
            "license_audit.cli.check.run_audit", return_value=AnalysisReport()
        ) as run:
            result = CliRunner().invoke(cli, ["--config", str(tmp_path), "check"])
        assert result.exit_code == 0
        assert run.call_args.args[2] == tmp_path


class TestCleanExits:
    def test_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_version(self) -> None:
        result = CliRunner().invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output

    def test_runtime_error_still_exits_one(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(cli, ["--target", str(tmp_path), "check"])
        assert result.exit_code == 1
        assert "No virtualenv found" in result.output

    def test_interrupt_exits_one(self) -> None:
        with patch.object(click.Group, "main", side_effect=click.Abort):
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 1
        assert "Aborted!" in result.output
