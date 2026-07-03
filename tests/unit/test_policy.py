"""Tests for PolicyEngine."""

from __future__ import annotations

from license_audit.config import LicenseAuditConfig
from license_audit.core.models import (
    LicenseCategory,
    LicensePolicy,
    LicenseSource,
    PackageLicense,
    PolicyLevel,
)
from license_audit.core.policy import PolicyEngine

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
_UNRECOGNIZED = PackageLicense(
    name="f",
    version="1.0",
    license_expression="Dual License",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.UNKNOWN,
)
# A declared-but-unrecognized license the user classified as permissive via the
# whitelist: the expression stays UNKNOWN but the category is now authoritative.
_CLASSIFIED_PERMISSIVE = PackageLicense(
    name="g",
    version="1.0",
    license_expression="UNKNOWN",
    declared_license="Proprietary License",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.PERMISSIVE,
    category_overridden=True,
)
_CLASSIFIED_STRONG = PackageLicense(
    name="h",
    version="1.0",
    license_expression="UNKNOWN",
    declared_license="Some Copyleft EULA",
    license_source=LicenseSource.METADATA,
    category=LicenseCategory.STRONG_COPYLEFT,
    category_overridden=True,
)


def _policy(
    policy_type: PolicyLevel = PolicyLevel.PERMISSIVE,
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


class TestIsUnknown:
    def test_literal_unknown_expression(self) -> None:
        assert PolicyEngine.is_unknown(_UNKNOWN) is True

    def test_unrecognized_expression(self) -> None:
        assert PolicyEngine.is_unknown(_UNRECOGNIZED) is True

    def test_known_license(self) -> None:
        assert PolicyEngine.is_unknown(_MIT) is False

    def test_copyleft_license(self) -> None:
        assert PolicyEngine.is_unknown(_GPL) is False

    def test_whitelisted_unknown_expression_is_not_unknown(self) -> None:
        # Expression is still "UNKNOWN" but the user assigned a real category.
        assert PolicyEngine.is_unknown(_CLASSIFIED_PERMISSIVE) is False


class TestMaxRank:
    def test_permissive_is_lowest(self) -> None:
        engine = PolicyEngine()
        assert engine.max_rank(PolicyLevel.PERMISSIVE) == 0

    def test_ranks_are_ordered(self) -> None:
        engine = PolicyEngine()
        permissive = engine.max_rank(PolicyLevel.PERMISSIVE)
        weak = engine.max_rank(PolicyLevel.WEAK_COPYLEFT)
        strong = engine.max_rank(PolicyLevel.STRONG_COPYLEFT)
        network = engine.max_rank(PolicyLevel.NETWORK_COPYLEFT)
        assert permissive is not None
        assert weak is not None
        assert strong is not None
        assert network is not None
        assert permissive < weak < strong < network


class TestExceedsRank:
    def test_permissive_pkg_within_permissive_policy(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.PERMISSIVE)
        assert engine.exceeds_rank(_MIT, max_rank) is False

    def test_copyleft_pkg_exceeds_permissive_policy(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.PERMISSIVE)
        assert engine.exceeds_rank(_GPL, max_rank) is True

    def test_weak_within_weak_policy(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.WEAK_COPYLEFT)
        assert engine.exceeds_rank(_LGPL, max_rank) is False

    def test_strong_exceeds_weak_policy(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.WEAK_COPYLEFT)
        assert engine.exceeds_rank(_GPL, max_rank) is True

    def test_agpl_exceeds_strong_copyleft_policy(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.STRONG_COPYLEFT)
        assert engine.exceeds_rank(_AGPL, max_rank) is True

    def test_agpl_within_network_copyleft_policy(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.NETWORK_COPYLEFT)
        assert engine.exceeds_rank(_AGPL, max_rank) is False

    def test_unknown_category_never_exceeds(self) -> None:
        engine = PolicyEngine()
        max_rank = engine.max_rank(PolicyLevel.PERMISSIVE)
        assert engine.exceeds_rank(_UNKNOWN, max_rank) is False

    def test_none_max_rank_allows_everything(self) -> None:
        assert PolicyEngine().exceeds_rank(_AGPL, None) is False


class TestCheck:
    def test_permissive_policy_passes_permissive(self) -> None:
        assert PolicyEngine().check([_MIT], _policy(PolicyLevel.PERMISSIVE)) is True

    def test_permissive_policy_rejects_weak(self) -> None:
        assert PolicyEngine().check([_LGPL], _policy(PolicyLevel.PERMISSIVE)) is False

    def test_permissive_policy_rejects_strong(self) -> None:
        assert PolicyEngine().check([_GPL], _policy(PolicyLevel.PERMISSIVE)) is False

    def test_permissive_policy_rejects_network(self) -> None:
        assert PolicyEngine().check([_AGPL], _policy(PolicyLevel.PERMISSIVE)) is False

    def test_weak_policy_passes_weak(self) -> None:
        assert PolicyEngine().check([_LGPL], _policy(PolicyLevel.WEAK_COPYLEFT)) is True

    def test_weak_policy_rejects_strong(self) -> None:
        assert PolicyEngine().check([_GPL], _policy(PolicyLevel.WEAK_COPYLEFT)) is False

    def test_strong_policy_passes_strong(self) -> None:
        assert (
            PolicyEngine().check([_GPL], _policy(PolicyLevel.STRONG_COPYLEFT)) is True
        )

    def test_strong_policy_rejects_network(self) -> None:
        assert (
            PolicyEngine().check([_AGPL], _policy(PolicyLevel.STRONG_COPYLEFT)) is False
        )

    def test_network_policy_passes_all(self) -> None:
        assert (
            PolicyEngine().check(
                [_MIT, _LGPL, _GPL, _AGPL],
                _policy(PolicyLevel.NETWORK_COPYLEFT),
            )
            is True
        )

    def test_fail_on_unknown_rejects_unknown(self) -> None:
        assert (
            PolicyEngine().check(
                [_UNKNOWN],
                _policy(PolicyLevel.PERMISSIVE, fail_on_unknown=True),
            )
            is False
        )

    def test_no_fail_on_unknown_passes_unknown(self) -> None:
        assert (
            PolicyEngine().check(
                [_UNKNOWN],
                _policy(PolicyLevel.PERMISSIVE, fail_on_unknown=False),
            )
            is True
        )

    def test_whitelisted_permissive_passes_even_with_fail_on_unknown(self) -> None:
        assert (
            PolicyEngine().check(
                [_CLASSIFIED_PERMISSIVE],
                _policy(PolicyLevel.PERMISSIVE, fail_on_unknown=True),
            )
            is True
        )

    def test_whitelisted_strong_copyleft_rejected_by_permissive_policy(self) -> None:
        # Deeming it strong-copyleft means a permissive policy must reject it.
        assert (
            PolicyEngine().check(
                [_CLASSIFIED_STRONG],
                _policy(PolicyLevel.PERMISSIVE, fail_on_unknown=True),
            )
            is False
        )

    def test_denied_list_rejects(self) -> None:
        assert (
            PolicyEngine().check(
                [_MIT],
                _policy(PolicyLevel.PERMISSIVE, denied=["MIT"]),
            )
            is False
        )

    def test_allowed_list_rejects_unlisted(self) -> None:
        assert (
            PolicyEngine().check(
                [_MIT],
                _policy(PolicyLevel.PERMISSIVE, allowed=["Apache-2.0"]),
            )
            is False
        )

    def test_allowed_list_passes_listed(self) -> None:
        assert (
            PolicyEngine().check(
                [_MIT],
                _policy(PolicyLevel.PERMISSIVE, allowed=["MIT"]),
            )
            is True
        )

    def test_mixed_packages_first_violation_fails(self) -> None:
        assert (
            PolicyEngine().check([_MIT, _GPL], _policy(PolicyLevel.PERMISSIVE)) is False
        )

    def test_fail_on_unknown_catches_unrecognized_expression(self) -> None:
        assert (
            PolicyEngine().check(
                [_UNRECOGNIZED],
                _policy(PolicyLevel.PERMISSIVE, fail_on_unknown=True),
            )
            is False
        )

    def test_no_fail_on_unknown_passes_unrecognized_expression(self) -> None:
        assert (
            PolicyEngine().check(
                [_UNRECOGNIZED],
                _policy(PolicyLevel.PERMISSIVE, fail_on_unknown=False),
            )
            is True
        )

    def test_or_expression_with_one_branch_denied_passes(self) -> None:
        pkg = PackageLicense(
            name="dual",
            version="1.0",
            license_expression="Apache-2.0 OR MIT",
            category=LicenseCategory.PERMISSIVE,
        )
        assert PolicyEngine().check([pkg], _policy(denied=["MIT"])) is True

    def test_or_expression_with_all_branches_denied_fails(self) -> None:
        pkg = PackageLicense(
            name="dual",
            version="1.0",
            license_expression="Apache-2.0 OR MIT",
            category=LicenseCategory.PERMISSIVE,
        )
        assert (
            PolicyEngine().check(
                [pkg],
                _policy(denied=["MIT", "Apache-2.0"]),
            )
            is False
        )

    def test_and_expression_with_one_branch_denied_fails(self) -> None:
        pkg = PackageLicense(
            name="weak",
            version="1.0",
            license_expression="MPL-2.0 AND MIT",
            category=LicenseCategory.WEAK_COPYLEFT,
        )
        assert (
            PolicyEngine().check(
                [pkg],
                _policy(PolicyLevel.WEAK_COPYLEFT, denied=["MPL-2.0"]),
            )
            is False
        )

    def test_or_expression_passes_when_one_branch_allowed(self) -> None:
        pkg = PackageLicense(
            name="dual",
            version="1.0",
            license_expression="Apache-2.0 OR MIT",
            category=LicenseCategory.PERMISSIVE,
        )
        assert PolicyEngine().check([pkg], _policy(allowed=["MIT"])) is True


class TestBuildActionItems:
    def test_denied_licenses_produce_errors(self) -> None:
        config = LicenseAuditConfig(denied_licenses=["MIT"])
        items = PolicyEngine().build_action_items([_MIT], [], config)
        denied_items = [
            i for i in items if i.severity == "error" and "denied" in i.message
        ]
        assert len(denied_items) == 1

    def test_or_expression_no_error_when_alt_avoids_denied(self) -> None:
        pkg = PackageLicense(
            name="dual",
            version="1.0",
            license_expression="Apache-2.0 OR MIT",
            category=LicenseCategory.PERMISSIVE,
        )
        config = LicenseAuditConfig(denied_licenses=["MIT"])
        items = PolicyEngine().build_action_items([pkg], [], config)
        denied_errors = [
            i for i in items if i.severity == "error" and "denied" in i.message
        ]
        assert denied_errors == []

    def test_and_expression_produces_error_when_required_license_denied(self) -> None:
        pkg = PackageLicense(
            name="weak",
            version="1.0",
            license_expression="MPL-2.0 AND MIT",
            category=LicenseCategory.WEAK_COPYLEFT,
        )
        config = LicenseAuditConfig(
            policy=PolicyLevel.WEAK_COPYLEFT,
            denied_licenses=["MPL-2.0"],
        )
        items = PolicyEngine().build_action_items([pkg], [], config)
        denied_errors = [
            i for i in items if i.severity == "error" and "denied" in i.message
        ]
        assert len(denied_errors) == 1
        assert "MPL-2.0" in denied_errors[0].message

    def test_unknown_produces_warning(self) -> None:
        items = PolicyEngine().build_action_items([_UNKNOWN], [], LicenseAuditConfig())
        warnings = [i for i in items if i.severity == "warning"]
        assert len(warnings) >= 1

    def test_not_detected_message_distinct_from_declared(self) -> None:
        # The not-found state must read differently from declared-but-unrecognized,
        # or requirement #2 (distinguishing the two) is lost at the policy layer.
        items = PolicyEngine().build_action_items([_UNKNOWN], [], LicenseAuditConfig())
        msg = next(i.message for i in items if i.package == _UNKNOWN.name)
        assert "could not be detected" in msg
        assert "declares license" not in msg

    def test_unrecognized_expression_warning(self) -> None:
        items = PolicyEngine().build_action_items(
            [_UNRECOGNIZED],
            [],
            LicenseAuditConfig(),
        )
        warnings = [i for i in items if "has no classification data" in i.message]
        assert len(warnings) == 1

    def test_whitelisted_permissive_produces_no_unknown_warning(self) -> None:
        items = PolicyEngine().build_action_items(
            [_CLASSIFIED_PERMISSIVE],
            [],
            LicenseAuditConfig(),
        )
        assert not any(
            i.package == _CLASSIFIED_PERMISSIVE.name and "unknown" in i.message.lower()
            for i in items
        )
        # A deemed-permissive package under a permissive policy is fully clean.
        assert items == []

    def test_deemed_copyleft_violation_names_declared_license(self) -> None:
        # The violation message must name the declared string the user
        # classified, not the bare "UNKNOWN" sentinel kept in the expression.
        items = PolicyEngine().build_action_items(
            [_CLASSIFIED_STRONG],
            [],
            LicenseAuditConfig(),  # permissive policy
        )
        errors = [i for i in items if i.package == _CLASSIFIED_STRONG.name]
        assert len(errors) == 1
        assert "Some Copyleft EULA" in errors[0].message
        assert "'UNKNOWN'" not in errors[0].message

    def test_declared_license_warning_names_raw_identifier(self) -> None:
        pkg = PackageLicense(
            name="proprietary-package",
            version="12.0",
            license_expression="UNKNOWN",
            declared_license="Proprietary License",
            license_source=LicenseSource.METADATA,
            category=LicenseCategory.UNKNOWN,
        )
        items = PolicyEngine().build_action_items([pkg], [], LicenseAuditConfig())
        warnings = [i for i in items if i.package == "proprietary-package"]
        assert len(warnings) == 1
        msg = warnings[0].message
        assert "Proprietary License" in msg
        assert "not a recognized SPDX identifier" in msg
        assert "Review its license text" in msg

    def test_and_expression_names_unclassifiable_component(self) -> None:
        """Pkg with a parseable expression where only one AND component is
        UNKNOWN should call out that component by name, not the whole expr."""
        pkg = PackageLicense(
            name="numpy",
            version="1.0",
            license_expression="BSD-3-Clause AND CC0-1.0",
            category=LicenseCategory.UNKNOWN,
        )
        items = PolicyEngine().build_action_items([pkg], [], LicenseAuditConfig())
        warnings = [
            i for i in items if i.severity == "warning" and i.package == "numpy"
        ]
        assert len(warnings) == 1
        msg = warnings[0].message
        assert "'CC0-1.0'" in msg
        assert "BSD-3-Clause" not in msg.split("in '")[0]  # Only in the expr echo
        assert "not a recognized SPDX" not in msg

    def test_denied_base_license_flags_with_exception_form(self) -> None:
        pkg = PackageLicense(
            name="jdk-lib",
            version="1.0",
            license_expression="GPL-2.0-only WITH Classpath-exception-2.0",
            category=LicenseCategory.WEAK_COPYLEFT,
        )
        items = PolicyEngine().denied_license_items([pkg], ["GPL-2.0-only"])
        assert len(items) == 1
        assert "GPL-2.0-only WITH Classpath-exception-2.0" in items[0].message

    def test_unparseable_expression_ignores_unrelated_denylist(self) -> None:
        pkg = PackageLicense(
            name="internal-tool",
            version="1.0",
            license_expression="Custom EULA v2 (internal)",
            category=LicenseCategory.UNKNOWN,
        )
        assert PolicyEngine().denied_license_items([pkg], ["GPL-3.0-only"]) == []

    def test_copyleft_warning_for_strong(self) -> None:
        config = LicenseAuditConfig(policy=PolicyLevel.NETWORK_COPYLEFT)
        items = PolicyEngine().build_action_items([_GPL], [], config)
        copyleft_warnings = [
            i for i in items if i.severity == "warning" and "copyleft" in i.message
        ]
        assert len(copyleft_warnings) >= 1

    def test_policy_violation_error(self) -> None:
        config = LicenseAuditConfig(policy=PolicyLevel.PERMISSIVE)
        items = PolicyEngine().build_action_items([_GPL], [], config)
        errors = [i for i in items if i.severity == "error" and "violates" in i.message]
        assert len(errors) == 1

    def test_allowed_license_violation_error(self) -> None:
        config = LicenseAuditConfig(allowed_licenses=["Apache-2.0"])
        items = PolicyEngine().build_action_items([_MIT], [], config)
        errors = [i for i in items if i.severity == "error" and i.package == "a"]
        assert len(errors) == 1
        assert "not in the allowed" in errors[0].message

    def test_allowed_license_on_list_produces_no_error(self) -> None:
        config = LicenseAuditConfig(allowed_licenses=["MIT"])
        items = PolicyEngine().build_action_items([_MIT], [], config)
        assert not [i for i in items if i.severity == "error"]


class TestBuildPolicy:
    def test_promotes_config_fields(self) -> None:
        config = LicenseAuditConfig(
            policy=PolicyLevel.STRONG_COPYLEFT,
            allowed_licenses=["MIT"],
            denied_licenses=["GPL-3.0-only"],
            fail_on_unknown=False,
        )
        policy = PolicyEngine().build_policy(config)
        assert policy.policy_type == PolicyLevel.STRONG_COPYLEFT
        assert policy.allowed_licenses == ["MIT"]
        assert policy.denied_licenses == ["GPL-3.0-only"]
        assert policy.fail_on_unknown is False
