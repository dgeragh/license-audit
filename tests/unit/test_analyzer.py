"""Tests for the analyzer orchestrator."""

from pathlib import Path

import pytest

from license_audit.config import LicenseAuditConfig
from license_audit.core.analyzer import (
    _POLICY_MAX_RANK,
    _build_action_items,
    _check_policy,
    _classify_package,
    _exceeds_policy_rank,
    _extract_spdx_ids,
    _is_unknown,
    analyze,
)
from license_audit.core.models import (
    UNKNOWN_LICENSE,
    LicenseCategory,
    LicensePolicy,
    LicenseSource,
    PackageLicense,
)


class TestAnalyze:
    def test_self_analysis(self) -> None:
        """Analyze license_audit's own dependencies via its .venv."""
        project_dir = Path(__file__).parent.parent.parent
        report = analyze(target=project_dir)
        assert report.project_name == "license-audit"
        assert len(report.packages) > 0
        assert report.policy_passed is not None

    def test_unknown_project(self, tmp_path: Path) -> None:
        """Analyze an empty directory raises FileNotFoundError (no source found)."""
        with pytest.raises(FileNotFoundError):
            analyze(target=tmp_path)

    def test_no_target_uses_current_env(self) -> None:
        """Analyze with no target uses the current environment."""
        report = analyze()
        assert report.project_name is not None


_MIT = PackageLicense(
    name="a",
    version="1.0",
    license_expression="MIT",
    license_source=LicenseSource.PEP639,
    category=LicenseCategory.PERMISSIVE,
)
_LGPL = PackageLicense(
    name="b",
    version="1.0",
    license_expression="LGPL-2.1-only",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.WEAK_COPYLEFT,
)
_GPL = PackageLicense(
    name="c",
    version="1.0",
    license_expression="GPL-3.0-only",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.STRONG_COPYLEFT,
)
_AGPL = PackageLicense(
    name="d",
    version="1.0",
    license_expression="AGPL-3.0-only",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.NETWORK_COPYLEFT,
)
_UNKNOWN = PackageLicense(
    name="e",
    version="1.0",
    license_expression="UNKNOWN",
    license_source=LicenseSource.UNKNOWN,
    category=LicenseCategory.UNKNOWN,
)
# Simulates a package like python-dateutil: has a non-UNKNOWN expression but
# the classifier can't recognize it, so category ends up UNKNOWN.
_UNRECOGNIZED = PackageLicense(
    name="f",
    version="1.0",
    license_expression="Dual License",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.UNKNOWN,
)


class TestIsUnknown:
    def test_literal_unknown_expression(self) -> None:
        assert _is_unknown(_UNKNOWN) is True

    def test_unrecognized_expression(self) -> None:
        assert _is_unknown(_UNRECOGNIZED) is True

    def test_known_license_is_not_unknown(self) -> None:
        assert _is_unknown(_MIT) is False

    def test_copyleft_is_not_unknown(self) -> None:
        assert _is_unknown(_GPL) is False


class TestPolicyMaxRank:
    def test_permissive_rank_is_zero(self) -> None:
        assert _POLICY_MAX_RANK["permissive"] == 0

    def test_all_policy_levels_present(self) -> None:
        assert set(_POLICY_MAX_RANK.keys()) == {
            "permissive",
            "weak-copyleft",
            "strong-copyleft",
            "network-copyleft",
        }

    def test_ranks_are_ordered(self) -> None:
        assert (
            _POLICY_MAX_RANK["permissive"]
            < _POLICY_MAX_RANK["weak-copyleft"]
            < _POLICY_MAX_RANK["strong-copyleft"]
            < _POLICY_MAX_RANK["network-copyleft"]
        )


class TestExceedsPolicyRank:
    def test_permissive_pkg_within_permissive_policy(self) -> None:
        assert _exceeds_policy_rank(_MIT, _POLICY_MAX_RANK["permissive"]) is False

    def test_copyleft_pkg_exceeds_permissive_policy(self) -> None:
        assert _exceeds_policy_rank(_GPL, _POLICY_MAX_RANK["permissive"]) is True

    def test_weak_copyleft_within_weak_copyleft_policy(self) -> None:
        assert _exceeds_policy_rank(_LGPL, _POLICY_MAX_RANK["weak-copyleft"]) is False

    def test_strong_copyleft_exceeds_weak_copyleft_policy(self) -> None:
        assert _exceeds_policy_rank(_GPL, _POLICY_MAX_RANK["weak-copyleft"]) is True

    def test_network_copyleft_exceeds_strong_copyleft_policy(self) -> None:
        assert _exceeds_policy_rank(_AGPL, _POLICY_MAX_RANK["strong-copyleft"]) is True

    def test_agpl_within_network_copyleft_policy(self) -> None:
        assert (
            _exceeds_policy_rank(_AGPL, _POLICY_MAX_RANK["network-copyleft"]) is False
        )

    def test_unknown_category_is_not_rejected(self) -> None:
        assert _exceeds_policy_rank(_UNKNOWN, _POLICY_MAX_RANK["permissive"]) is False

    def test_none_max_rank_allows_everything(self) -> None:
        assert _exceeds_policy_rank(_AGPL, None) is False


class TestCheckPolicyEnforcement:
    """Test that _check_policy correctly enforces policy_type."""

    def _policy(
        self,
        policy_type: str = "permissive",
        fail_on_unknown: bool = False,
        denied: list[str] | None = None,
        allowed: list[str] | None = None,
    ) -> LicensePolicy:
        return LicensePolicy(
            policy_type=policy_type,
            fail_on_unknown=fail_on_unknown,
            denied_licenses=denied or [],
            allowed_licenses=allowed or [],
        )

    def test_permissive_policy_passes_permissive(self) -> None:
        assert _check_policy([_MIT], self._policy("permissive")) is True

    def test_permissive_policy_rejects_weak_copyleft(self) -> None:
        assert _check_policy([_LGPL], self._policy("permissive")) is False

    def test_permissive_policy_rejects_strong_copyleft(self) -> None:
        assert _check_policy([_GPL], self._policy("permissive")) is False

    def test_permissive_policy_rejects_network_copyleft(self) -> None:
        assert _check_policy([_AGPL], self._policy("permissive")) is False

    def test_weak_copyleft_policy_passes_weak(self) -> None:
        assert _check_policy([_LGPL], self._policy("weak-copyleft")) is True

    def test_weak_copyleft_policy_rejects_strong(self) -> None:
        assert _check_policy([_GPL], self._policy("weak-copyleft")) is False

    def test_strong_copyleft_policy_passes_strong(self) -> None:
        assert _check_policy([_GPL], self._policy("strong-copyleft")) is True

    def test_strong_copyleft_policy_rejects_network(self) -> None:
        assert _check_policy([_AGPL], self._policy("strong-copyleft")) is False

    def test_network_copyleft_policy_passes_all(self) -> None:
        assert (
            _check_policy([_MIT, _LGPL, _GPL, _AGPL], self._policy("network-copyleft"))
            is True
        )

    def test_fail_on_unknown_rejects_unknown(self) -> None:
        assert (
            _check_policy([_UNKNOWN], self._policy("permissive", fail_on_unknown=True))
            is False
        )

    def test_no_fail_on_unknown_passes_unknown(self) -> None:
        assert (
            _check_policy([_UNKNOWN], self._policy("permissive", fail_on_unknown=False))
            is True
        )

    def test_denied_list_rejects(self) -> None:
        assert (
            _check_policy([_MIT], self._policy("permissive", denied=["MIT"])) is False
        )

    def test_allowed_list_rejects_unlisted(self) -> None:
        assert (
            _check_policy([_MIT], self._policy("permissive", allowed=["Apache-2.0"]))
            is False
        )

    def test_allowed_list_passes_listed(self) -> None:
        assert (
            _check_policy([_MIT], self._policy("permissive", allowed=["MIT"])) is True
        )

    def test_mixed_packages_first_violation_fails(self) -> None:
        """Even if one package passes, a violating package fails the whole check."""
        assert _check_policy([_MIT, _GPL], self._policy("permissive")) is False

    def test_fail_on_unknown_catches_unrecognized_expression(self) -> None:
        """A non-'UNKNOWN' expression with unknown category should still fail."""
        assert (
            _check_policy(
                [_UNRECOGNIZED], self._policy("permissive", fail_on_unknown=True)
            )
            is False
        )

    def test_no_fail_on_unknown_passes_unrecognized_expression(self) -> None:
        assert (
            _check_policy(
                [_UNRECOGNIZED], self._policy("permissive", fail_on_unknown=False)
            )
            is True
        )


class TestClassifyPackage:
    def test_single_license(self) -> None:
        pkg = PackageLicense(name="a", version="1.0", license_expression="MIT")
        _classify_package(pkg)
        assert pkg.category == LicenseCategory.PERMISSIVE

    def test_or_expression_picks_most_permissive(self) -> None:
        pkg = PackageLicense(
            name="a", version="1.0", license_expression="MIT OR GPL-3.0-only"
        )
        _classify_package(pkg)
        assert pkg.category == LicenseCategory.PERMISSIVE

    def test_unknown_expression_not_classified(self) -> None:
        pkg = PackageLicense(
            name="a", version="1.0", license_expression=UNKNOWN_LICENSE
        )
        _classify_package(pkg)
        # Should remain UNKNOWN since _classify_package is not called for UNKNOWN
        assert pkg.category == LicenseCategory.UNKNOWN


class TestExtractSpdxIds:
    def test_skips_unknown(self) -> None:
        result = _extract_spdx_ids(["MIT", UNKNOWN_LICENSE, "Apache-2.0"])
        assert "MIT" in result
        assert "Apache-2.0" in result
        assert UNKNOWN_LICENSE not in result

    def test_empty_list(self) -> None:
        assert _extract_spdx_ids([]) == []


class TestBuildActionItems:
    def test_denied_licenses_produce_errors(self) -> None:
        config = LicenseAuditConfig(denied_licenses=["MIT"])
        items = _build_action_items([_MIT], [], config)
        denied_items = [
            i for i in items if i.severity == "error" and "denied" in i.message
        ]
        assert len(denied_items) == 1

    def test_unknown_produces_warning(self) -> None:
        config = LicenseAuditConfig()
        items = _build_action_items([_UNKNOWN], [], config)
        warning_items = [i for i in items if i.severity == "warning"]
        assert len(warning_items) >= 1

    def test_unrecognized_expression_warning(self) -> None:
        config = LicenseAuditConfig()
        items = _build_action_items([_UNRECOGNIZED], [], config)
        warning_items = [i for i in items if "not a recognized SPDX" in i.message]
        assert len(warning_items) == 1

    def test_copyleft_warning_for_strong(self) -> None:
        config = LicenseAuditConfig(policy="network-copyleft")
        items = _build_action_items([_GPL], [], config)
        copyleft_warnings = [
            i for i in items if i.severity == "warning" and "copyleft" in i.message
        ]
        assert len(copyleft_warnings) >= 1

    def test_policy_violation_error(self) -> None:
        config = LicenseAuditConfig(policy="permissive")
        items = _build_action_items([_GPL], [], config)
        errors = [i for i in items if i.severity == "error" and "violates" in i.message]
        assert len(errors) == 1
