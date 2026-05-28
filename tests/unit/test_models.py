"""Tests for core data models."""

from __future__ import annotations

from license_audit.core.models import LicenseCategory, LicenseSource, PackageLicense


class TestDisplayLicense:
    def test_recognized_license_uses_expression(self) -> None:
        pkg = PackageLicense(
            name="click",
            version="8.1.0",
            license_expression="BSD-3-Clause",
            license_source=LicenseSource.PEP639,
            category=LicenseCategory.PERMISSIVE,
        )
        assert pkg.display_license == "BSD-3-Clause"

    def test_declared_string_preferred_when_present(self) -> None:
        pkg = PackageLicense(
            name="proprietary-package",
            version="12.0.0",
            license_expression="UNKNOWN",
            declared_license="Proprietary License",
            license_source=LicenseSource.METADATA,
            category=LicenseCategory.UNKNOWN,
        )
        assert pkg.display_license == "Proprietary License"

    def test_undetected_license_falls_back_to_unknown(self) -> None:
        pkg = PackageLicense(name="mystery", version="1.0.0")
        assert pkg.declared_license is None
        assert pkg.display_license == "UNKNOWN"
