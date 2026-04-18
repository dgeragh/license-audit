"""Tests for the report CLI command."""

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


class TestReportCli:
    def test_markdown_output(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.report.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["report"])
        assert result.exit_code == 0
        assert "test-project" in result.output

    def test_json_output(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.report.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["report", "--format", "json"])
        assert result.exit_code == 0
        assert '"project_name"' in result.output

    def test_output_to_file(self, tmp_path) -> None:
        report = _make_report(packages=[_MIT_PKG])
        out = tmp_path / "report.md"
        with patch("license_audit.cli.report.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["report", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "test-project" in out.read_text()

    def test_notices_output(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.report.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["report", "--format", "notices"])
        assert result.exit_code == 0
        assert "Third-Party Notices" in result.output
        assert "good-pkg" in result.output

    def test_notices_output_to_file(self, tmp_path) -> None:
        pkg = PackageLicense(
            name="licensed-pkg",
            version="2.0.0",
            license_expression="Apache-2.0",
            license_source=LicenseSource.PEP639,
            category=LicenseCategory.PERMISSIVE,
            license_text="Copyright 2024 Test Corp\nApache License 2.0",
        )
        report = _make_report(packages=[pkg])
        out = tmp_path / "THIRD_PARTY_NOTICES.md"
        with patch("license_audit.cli.report.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(
                cli, ["report", "--format", "notices", "--output", str(out)]
            )
        assert result.exit_code == 0
        assert out.exists()
        content = out.read_text()
        assert "Third-Party Notices" in content
        assert "licensed-pkg" in content
        assert "Copyright 2024 Test Corp" in content

    def test_invalid_format_rejected(self) -> None:
        result = CliRunner().invoke(cli, ["report", "--format", "csv"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestReportPolicyFlag:
    def test_policy_passed_to_analyzer(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.report.run_audit", return_value=report) as mock:
            result = CliRunner().invoke(cli, ["--policy", "strong-copyleft", "report"])
        assert result.exit_code == 0
        config = mock.call_args.args[1]
        assert config is not None
        assert config.policy == "strong-copyleft"
