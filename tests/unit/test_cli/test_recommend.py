"""Tests for the recommend CLI command."""

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
    recommended_licenses: list[str] | None = None,
) -> AnalysisReport:
    return AnalysisReport(
        project_name="test-project",
        packages=packages or [],
        recommended_licenses=recommended_licenses or [],
    )


_MIT_PKG = PackageLicense(
    name="good-pkg",
    version="1.0.0",
    license_expression="MIT",
    license_source=LicenseSource.PEP639,
    category=LicenseCategory.PERMISSIVE,
)

_GPL_PKG = PackageLicense(
    name="gpl-pkg",
    version="2.0.0",
    license_expression="GPL-3.0-only",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.STRONG_COPYLEFT,
)


class TestRecommendCli:
    def test_basic_output(self) -> None:
        report = _make_report(
            packages=[_MIT_PKG],
            recommended_licenses=["MIT", "Apache-2.0"],
        )
        with patch("license_audit.cli.recommend.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "test-project" in result.output

    def test_no_packages(self) -> None:
        report = _make_report(packages=[])
        with patch("license_audit.cli.recommend.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "No dependencies found" in result.output

    def test_no_compatible_licenses(self) -> None:
        report = _make_report(
            packages=[_GPL_PKG],
            recommended_licenses=[],
        )
        with patch("license_audit.cli.recommend.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "No compatible" in result.output


class TestRecommendActionItems:
    def test_action_items_shown(self) -> None:
        from license_audit.core.models import ActionItem

        report = _make_report(
            packages=[_GPL_PKG],
            recommended_licenses=["GPL-3.0-only"],
        )
        report.action_items = [
            ActionItem(
                severity="warning",
                package="gpl-pkg",
                message="Copyleft license detected.",
            )
        ]
        with patch("license_audit.cli.recommend.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "Action items" in result.output

    def test_incompatible_pairs_shown(self) -> None:
        from license_audit.core.models import CompatibilityResult, Verdict

        report = _make_report(
            packages=[_GPL_PKG],
            recommended_licenses=[],
        )
        report.incompatible_pairs = [
            CompatibilityResult(
                inbound="GPL-2.0-only",
                outbound="Apache-2.0",
                verdict=Verdict.INCOMPATIBLE,
            )
        ]
        with patch("license_audit.cli.recommend.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "GPL-2.0-only" in result.output


class TestRecommendPolicyFlag:
    def test_policy_passed_to_analyzer(self) -> None:
        report = _make_report(
            packages=[_MIT_PKG],
            recommended_licenses=["MIT"],
        )
        with patch("license_audit.cli.recommend.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(
                cli, ["--policy", "network-copyleft", "recommend"]
            )
        assert result.exit_code == 0
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config is not None
        assert config.policy == "network-copyleft"
