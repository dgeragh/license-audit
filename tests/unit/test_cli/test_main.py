"""Tests for the CLI group's exit-code handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click
from click.testing import CliRunner

from license_audit.cli.main import cli


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
