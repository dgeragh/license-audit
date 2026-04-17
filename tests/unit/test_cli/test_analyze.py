"""Tests for the analyze CLI command."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from license_audit.cli.main import cli
from license_audit.core.models import (
    AnalysisReport,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
)


def _make_report(
    packages: list[PackageLicense] | None = None,
) -> AnalysisReport:
    return AnalysisReport(
        project_name="test-project",
        packages=packages or [],
    )


_MIT_PKG = PackageLicense(
    name="good-pkg",
    version="1.0.0",
    license_expression="MIT",
    license_source=LicenseSource.PEP639,
    category=LicenseCategory.PERMISSIVE,
)


class TestAnalyzeCli:
    def test_terminal_output(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.analyze.LicenseAuditor") as mock_cls:
            mock_cls.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["analyze"])
        assert result.exit_code == 0

    def test_json_output(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.analyze.LicenseAuditor") as mock_cls:
            mock_cls.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["analyze", "--format", "json"])
        assert result.exit_code == 0
        assert '"project_name"' in result.output

    def test_invalid_format_rejected(self) -> None:
        result = CliRunner().invoke(cli, ["analyze", "--format", "csv"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestAnalyzePolicyFlag:
    def test_policy_passed_to_analyzer(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.analyze.LicenseAuditor") as mock_cls:
            mock_cls.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["--policy", "weak-copyleft", "analyze"])
        assert result.exit_code == 0
        config = mock_cls.return_value.run.call_args.kwargs.get("config")
        assert config is not None
        assert config.policy == "weak-copyleft"

    def test_no_policy_uses_config_default(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.analyze.LicenseAuditor") as mock_cls:
            mock_cls.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["analyze"])
        assert result.exit_code == 0
        config = mock_cls.return_value.run.call_args.kwargs.get("config")
        assert config is not None
        assert config.policy == "permissive"
