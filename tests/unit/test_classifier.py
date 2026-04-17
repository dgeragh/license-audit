"""Tests for LicenseClassifier."""

from __future__ import annotations

from license_audit._data import OSADLDataStore
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import LicenseCategory


class TestLicenseClassifier:
    def test_mit_is_permissive(self) -> None:
        assert LicenseClassifier().classify("MIT") == LicenseCategory.PERMISSIVE

    def test_apache_is_permissive(self) -> None:
        assert LicenseClassifier().classify("Apache-2.0") == LicenseCategory.PERMISSIVE

    def test_bsd3_is_permissive(self) -> None:
        assert (
            LicenseClassifier().classify("BSD-3-Clause") == LicenseCategory.PERMISSIVE
        )

    def test_gpl3_is_strong_copyleft(self) -> None:
        assert (
            LicenseClassifier().classify("GPL-3.0-only")
            == LicenseCategory.STRONG_COPYLEFT
        )

    def test_lgpl_is_weak_copyleft(self) -> None:
        assert (
            LicenseClassifier().classify("LGPL-2.1-only")
            == LicenseCategory.WEAK_COPYLEFT
        )

    def test_agpl_is_network_copyleft(self) -> None:
        assert (
            LicenseClassifier().classify("AGPL-3.0-only")
            == LicenseCategory.NETWORK_COPYLEFT
        )

    def test_unknown_license(self) -> None:
        assert LicenseClassifier().classify("NONEXISTENT") == LicenseCategory.UNKNOWN

    def test_is_network_copyleft(self) -> None:
        c = LicenseClassifier()
        assert c.is_network_copyleft("AGPL-3.0-only") is True
        assert c.is_network_copyleft("MIT") is False

    def test_accepts_injected_store(self) -> None:
        store = OSADLDataStore()
        classifier = LicenseClassifier(store=store)
        assert classifier.classify("MIT") == LicenseCategory.PERMISSIVE
