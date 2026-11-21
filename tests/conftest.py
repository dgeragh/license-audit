"""Shared test fixtures."""

from __future__ import annotations

import pytest

from license_audit.core.models import (
    ActionCode,
    ActionItem,
    AnalysisReport,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
)


@pytest.fixture()
def mit_package() -> PackageLicense:
    return PackageLicense(
        name="test-pkg",
        version="1.0.0",
        license_expression="MIT",
        license_source=LicenseSource.PEP639,
        category=LicenseCategory.PERMISSIVE,
    )


@pytest.fixture()
def gpl_package() -> PackageLicense:
    return PackageLicense(
        name="gpl-pkg",
        version="2.0.0",
        license_expression="GPL-3.0-only",
        license_source=LicenseSource.METADATA,
        category=LicenseCategory.STRONG_COPYLEFT,
    )


@pytest.fixture()
def sample_report(
    mit_package: PackageLicense, gpl_package: PackageLicense
) -> AnalysisReport:
    return AnalysisReport(
        project_name="test-project",
        packages=[mit_package, gpl_package],
        recommended_licenses=["GPL-3.0-only", "GPL-3.0-or-later", "AGPL-3.0-only"],
        action_items=[
            ActionItem(
                code=ActionCode.COPYLEFT_DEPENDENCY,
                severity="warning",
                package="gpl-pkg",
                message="Package 'gpl-pkg' uses strong-copyleft license 'GPL-3.0-only'.",
            )
        ],
        policy_passed=True,
    )
