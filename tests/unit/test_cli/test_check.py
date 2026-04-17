"""Tests for the check CLI command."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from license_audit.cli.main import cli
from license_audit.core.models import (
    ActionItem,
    AnalysisReport,
    CompatibilityResult,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
    Verdict,
)


def _make_report(
    packages: list[PackageLicense] | None = None,
    incompatible_pairs: list[CompatibilityResult] | None = None,
    policy_passed: bool | None = True,
    action_items: list[ActionItem] | None = None,
) -> AnalysisReport:
    return AnalysisReport(
        project_name="test-project",
        packages=packages or [],
        incompatible_pairs=incompatible_pairs or [],
        policy_passed=policy_passed,
        action_items=action_items or [],
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

_UNKNOWN_PKG = PackageLicense(
    name="mystery-pkg",
    version="0.1.0",
    license_expression="UNKNOWN",
    license_source=LicenseSource.UNKNOWN,
    category=LicenseCategory.UNKNOWN,
)

_LGPL_PKG = PackageLicense(
    name="lgpl-pkg",
    version="1.0.0",
    license_expression="LGPL-2.1-only",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.WEAK_COPYLEFT,
)

_AGPL_PKG = PackageLicense(
    name="agpl-pkg",
    version="1.0.0",
    license_expression="AGPL-3.0-only",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.NETWORK_COPYLEFT,
)

_UNRECOGNIZED_PKG = PackageLicense(
    name="dateutil-pkg",
    version="2.9.0",
    license_expression="Dual License",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.UNKNOWN,
)


class TestCheckPasses:
    def test_all_permissive(self) -> None:
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_no_fail_on_unknown(self) -> None:
        report = _make_report(packages=[_UNKNOWN_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check", "--no-fail-on-unknown"])
        assert result.exit_code == 0


class TestCheckFailsPolicyViolation:
    def test_exit_code_1_on_incompatible_pairs(self) -> None:
        pair = CompatibilityResult(
            inbound="GPL-3.0-only",
            outbound="Apache-2.0",
            verdict=Verdict.INCOMPATIBLE,
        )
        report = _make_report(
            packages=[_MIT_PKG, _GPL_PKG],
            incompatible_pairs=[pair],
        )
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "GPL-3.0-only" in result.output

    def test_exit_code_1_on_policy_failed(self) -> None:
        report = _make_report(
            packages=[_GPL_PKG],
            policy_passed=False,
            action_items=[
                ActionItem(
                    severity="error",
                    package="gpl-pkg",
                    message="Package 'gpl-pkg' uses strong-copyleft license 'GPL-3.0-only', which violates the 'permissive' policy.",
                )
            ],
        )
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "gpl-pkg" in result.output

    def test_policy_failed_shows_warnings(self) -> None:
        """When policy fails, warning-level action items should also be shown."""
        report = _make_report(
            packages=[_UNRECOGNIZED_PKG],
            policy_passed=False,
            action_items=[
                ActionItem(
                    severity="warning",
                    package="dateutil-pkg",
                    message="License 'Dual License' for 'dateutil-pkg' is not a recognized SPDX expression. Add an override in [tool.license-audit.overrides] or check manually.",
                )
            ],
        )
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 1
        assert "dateutil-pkg" in result.output
        assert "[tool.license-audit.overrides]" in result.output


class TestCheckFailsUnknown:
    def test_exit_code_2_on_unknown_with_fail_on_unknown(self) -> None:
        report = _make_report(packages=[_MIT_PKG, _UNKNOWN_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 2
        assert "UNKNOWN" in result.output
        assert "mystery-pkg" in result.output

    def test_no_fail_on_unknown_skips_exit_2(self) -> None:
        report = _make_report(packages=[_MIT_PKG, _UNKNOWN_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check", "--no-fail-on-unknown"])
        assert result.exit_code == 0

    def test_unrecognized_expression_detected_as_unknown(self) -> None:
        """A package with a non-SPDX expression (like 'Dual License') should
        be caught by the unknown check even though expression != 'UNKNOWN'."""
        report = _make_report(packages=[_MIT_PKG, _UNRECOGNIZED_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check"])
        assert result.exit_code == 2
        assert "dateutil-pkg" in result.output

    def test_unrecognized_expression_passes_with_no_fail_on_unknown(self) -> None:
        report = _make_report(packages=[_MIT_PKG, _UNRECOGNIZED_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check", "--no-fail-on-unknown"])
        assert result.exit_code == 0


class TestCheckPolicyFlag:
    """Test the --policy CLI flag on the check command."""

    def test_policy_permissive_rejects_copyleft(self) -> None:
        """With --policy permissive, a copyleft dep should fail."""
        report = _make_report(
            packages=[_MIT_PKG, _GPL_PKG],
            policy_passed=False,
            action_items=[
                ActionItem(
                    severity="error",
                    package="gpl-pkg",
                    message="Policy violation.",
                )
            ],
        )
        with patch("license_audit.cli.check.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["--policy", "permissive", "check"])
        assert result.exit_code == 1
        # Verify the config passed to analyze has the policy set
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config is not None
        assert config.policy == "permissive"

    def test_policy_strong_copyleft_accepts_gpl(self) -> None:
        """With --policy strong-copyleft, GPL deps should pass."""
        report = _make_report(packages=[_MIT_PKG, _GPL_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["--policy", "strong-copyleft", "check"])
        assert result.exit_code == 0
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config.policy == "strong-copyleft"

    def test_policy_weak_copyleft_accepts_lgpl(self) -> None:
        report = _make_report(packages=[_MIT_PKG, _LGPL_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["--policy", "weak-copyleft", "check"])
        assert result.exit_code == 0
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config.policy == "weak-copyleft"

    def test_policy_network_copyleft(self) -> None:
        report = _make_report(packages=[_MIT_PKG, _AGPL_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["--policy", "network-copyleft", "check"])
        assert result.exit_code == 0
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config.policy == "network-copyleft"

    def test_invalid_policy_rejected(self) -> None:
        result = CliRunner().invoke(cli, ["--policy", "yolo", "check"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_policy_flag_overrides_config(self) -> None:
        """--policy flag should override whatever is in pyproject.toml."""
        report = _make_report(packages=[_MIT_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["--policy", "network-copyleft", "check"])
        assert result.exit_code == 0
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config.policy == "network-copyleft"


class TestCheckFailOnUnknownFlag:
    def test_fail_on_unknown_flag_overrides_config(self) -> None:
        report = _make_report(packages=[_UNKNOWN_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as mock:
            mock.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check", "--no-fail-on-unknown"])
        assert result.exit_code == 0
        config = mock.return_value.run.call_args.kwargs.get("config")
        assert config.fail_on_unknown is False

    def test_fail_on_unknown_explicit_true(self) -> None:
        report = _make_report(packages=[_MIT_PKG, _UNKNOWN_PKG])
        with patch("license_audit.cli.check.LicenseAuditor") as _m:
            _m.return_value.run.return_value = report
            result = CliRunner().invoke(cli, ["check", "--fail-on-unknown"])
        assert result.exit_code == 2
