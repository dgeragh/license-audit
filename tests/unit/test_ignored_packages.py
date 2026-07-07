"""Tests for the ignored-packages exemption mechanism."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from license_audit.config import LicenseAuditConfig
from license_audit.core.analyzer import LicenseAuditor
from license_audit.core.models import (
    LicenseCategory,
    LicenseSource,
    PackageLicense,
    PolicyLevel,
)
from license_audit.core.policy import PolicyEngine


def _pkg(
    name: str,
    category: LicenseCategory = LicenseCategory.PERMISSIVE,
    license_expression: str = "MIT",
    ignored: bool = False,
    ignore_reason: str = "",
) -> PackageLicense:
    return PackageLicense(
        name=name,
        version="1.0",
        license_expression=license_expression,
        license_source=LicenseSource.PEP639,
        category=category,
        ignored=ignored,
        ignore_reason=ignore_reason,
    )


class TestConfigValidation:
    def test_empty_default(self) -> None:
        config = LicenseAuditConfig()
        assert config.ignored_packages == {}

    def test_valid_entries(self) -> None:
        config = LicenseAuditConfig(
            ignored_packages={"pandas-stubs": "reviewed manually"},
        )
        assert config.ignored_packages == {"pandas-stubs": "reviewed manually"}

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty string"):
            LicenseAuditConfig(ignored_packages={"pandas-stubs": ""})

    def test_whitespace_reason_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty string"):
            LicenseAuditConfig(ignored_packages={"pandas-stubs": "   "})

    def test_non_string_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LicenseAuditConfig(ignored_packages={"pandas-stubs": 123})  # type: ignore[dict-item]

    def test_non_dict_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LicenseAuditConfig(ignored_packages=["pandas-stubs"])  # type: ignore[arg-type]


class TestPolicyEngineSkipsIgnored:
    def _config(
        self,
        policy: PolicyLevel = PolicyLevel.PERMISSIVE,
        ignored: dict[str, str] | None = None,
        denied: list[str] | None = None,
        fail_on_unknown: bool = True,
    ) -> LicenseAuditConfig:
        return LicenseAuditConfig(
            policy=policy,
            ignored_packages=ignored or {},
            denied_licenses=denied or [],
            fail_on_unknown=fail_on_unknown,
        )

    def test_check_passes_when_violating_package_is_ignored(self) -> None:
        gpl = _pkg(
            "gpl_pkg",
            category=LicenseCategory.STRONG_COPYLEFT,
            license_expression="GPL-3.0-only",
            ignored=True,
            ignore_reason="manually reviewed",
        )
        config = self._config(policy=PolicyLevel.PERMISSIVE)
        policy = PolicyEngine().build_policy(config)
        assert PolicyEngine().check([gpl], policy) is True

    def test_check_fails_when_ignored_pkg_alongside_violating_pkg(self) -> None:
        gpl_ignored = _pkg(
            "gpl_ignored",
            category=LicenseCategory.STRONG_COPYLEFT,
            license_expression="GPL-3.0-only",
            ignored=True,
            ignore_reason="reviewed",
        )
        lgpl = _pkg(
            "lgpl_real",
            category=LicenseCategory.WEAK_COPYLEFT,
            license_expression="LGPL-2.1-only",
        )
        config = self._config(policy=PolicyLevel.PERMISSIVE)
        policy = PolicyEngine().build_policy(config)
        assert PolicyEngine().check([gpl_ignored, lgpl], policy) is False

    def test_check_skips_unknown_on_ignored_package(self) -> None:
        unknown = _pkg(
            "mystery",
            category=LicenseCategory.UNKNOWN,
            license_expression="UNKNOWN",
            ignored=True,
            ignore_reason="internal package",
        )
        config = self._config(fail_on_unknown=True)
        policy = PolicyEngine().build_policy(config)
        assert PolicyEngine().check([unknown], policy) is True

    def test_check_skips_denied_on_ignored_package(self) -> None:
        mit_ignored = _pkg(
            "mit_ignored",
            ignored=True,
            ignore_reason="reviewed",
        )
        config = self._config(denied=["MIT"])
        policy = PolicyEngine().build_policy(config)
        assert PolicyEngine().check([mit_ignored], policy) is True

    def test_action_items_skip_ignored(self) -> None:
        gpl_ignored = _pkg(
            "gpl_ignored",
            category=LicenseCategory.STRONG_COPYLEFT,
            license_expression="GPL-3.0-only",
            ignored=True,
            ignore_reason="reviewed",
        )
        config = self._config(policy=PolicyLevel.PERMISSIVE)
        items = PolicyEngine().build_action_items([gpl_ignored], [], config)
        assert items == []


class TestAuditorAppliesIgnores:
    def test_canonicalized_name_match(self) -> None:
        """`pandas-stubs` in config should match package name `pandas_stubs`."""
        auditor = LicenseAuditor()
        packages = [
            _pkg("pandas_stubs", category=LicenseCategory.PERMISSIVE),
            _pkg("other", category=LicenseCategory.PERMISSIVE),
        ]
        auditor._apply_ignores(packages, {"pandas-stubs": "reviewed"})
        assert packages[0].ignored is True
        assert packages[0].ignore_reason == "reviewed"
        assert packages[1].ignored is False

    def test_empty_ignore_map_noop(self) -> None:
        auditor = LicenseAuditor()
        packages = [_pkg("foo")]
        auditor._apply_ignores(packages, {})
        assert packages[0].ignored is False

    def test_non_matching_name_unchanged(self) -> None:
        auditor = LicenseAuditor()
        packages = [_pkg("foo")]
        auditor._apply_ignores(packages, {"bar": "wrong pkg"})
        assert packages[0].ignored is False
