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
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "test-project" in result.output

    def test_no_packages(self) -> None:
        report = _make_report(packages=[])
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "No dependencies found" in result.output

    def test_no_compatible_licenses(self) -> None:
        report = _make_report(
            packages=[_GPL_PKG],
            recommended_licenses=[],
        )
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
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
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
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
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "GPL-2.0-only" in result.output


class TestRecommendPolicyFlag:
    def test_policy_passed_to_analyzer(self) -> None:
        report = _make_report(
            packages=[_MIT_PKG],
            recommended_licenses=["MIT"],
        )
        with patch(
            "license_audit.cli.recommend.run_audit", return_value=report
        ) as mock:
            result = CliRunner().invoke(
                cli, ["--policy", "network-copyleft", "recommend"]
            )
        assert result.exit_code == 0
        config = mock.call_args.args[1]
        assert config is not None
        assert config.policy == "network-copyleft"


class TestRecommendSource:
    def test_source_displayed(self) -> None:
        report = _make_report(packages=[_MIT_PKG], recommended_licenses=["MIT"])
        report.source = "/abs/.venv"
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "Source:" in result.output
        assert "/abs/.venv" in result.output


_UNKNOWN_PKG = PackageLicense(
    name="weird-license-pkg",
    version="1.0.0",
    license_expression="BSD-3-Clause AND CC0-1.0",
    license_source=LicenseSource.PEP639,
    category=LicenseCategory.UNKNOWN,
)


class TestRecommendUnknownPackages:
    def test_unknown_blocks_recommendation_message(self) -> None:
        report = _make_report(
            packages=[_MIT_PKG, _UNKNOWN_PKG],
            recommended_licenses=[],
        )
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "Cannot recommend a license" in result.output
        assert "weird-license-pkg" in result.output
        assert "No compatible" not in result.output

    def test_ignored_unknown_doesnt_block(self) -> None:
        ignored_unknown = PackageLicense(
            name="ignored-unknown",
            version="1.0",
            license_expression="Custom-License",
            license_source=LicenseSource.METADATA,
            category=LicenseCategory.UNKNOWN,
            ignored=True,
            ignore_reason="Reviewed",
        )
        report = _make_report(
            packages=[_MIT_PKG, ignored_unknown],
            recommended_licenses=["MIT", "Apache-2.0"],
        )
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "Cannot recommend" not in result.output
        assert "MIT" in result.output


class TestRecommendIgnoredPackages:
    def test_ignored_gpl_does_not_drive_constraint(self) -> None:
        ignored_gpl = PackageLicense(
            name="ignored-gpl",
            version="1.0.0",
            license_expression="GPL-3.0-or-later",
            license_source=LicenseSource.CLASSIFIER,
            category=LicenseCategory.STRONG_COPYLEFT,
            ignored=True,
            ignore_reason="Reviewed manually",
        )
        report = _make_report(
            packages=[_MIT_PKG, ignored_gpl],
            recommended_licenses=["MIT", "Apache-2.0", "BSD-3-Clause"],
        )
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "Most restrictive dependency" not in result.output
        assert "ignored-gpl" not in result.output
        assert "GPL-compatible" not in result.output
        assert "Common choices: MIT" in result.output

    def test_constraint_with_bracketed_license_expression_preserved(self) -> None:
        bracketed = PackageLicense(
            name="weird_pkg",
            version="1.0",
            license_expression="GPL-3.0-only [internal note]",
            license_source=LicenseSource.OVERRIDE,
            category=LicenseCategory.STRONG_COPYLEFT,
        )
        report = _make_report(
            packages=[bracketed],
            recommended_licenses=["GPL-3.0-only"],
        )
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "[internal note]" in result.output

    def test_active_gpl_still_drives_constraint(self) -> None:
        """Sanity check: a non-ignored GPL package still surfaces as the
        most restrictive dependency."""
        report = _make_report(
            packages=[_MIT_PKG, _GPL_PKG],
            recommended_licenses=["GPL-3.0-only"],
        )
        with patch("license_audit.cli.recommend.run_audit", return_value=report) as _m:
            result = CliRunner().invoke(cli, ["recommend"])
        assert result.exit_code == 0
        assert "Most restrictive dependency" in result.output
        assert "gpl-pkg" in result.output
