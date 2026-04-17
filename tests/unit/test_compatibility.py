"""Tests for CompatibilityMatrix."""

from __future__ import annotations

from license_audit._data import OSADLDataStore
from license_audit.core.compatibility import CompatibilityMatrix
from license_audit.core.models import Verdict


class TestIsCompatible:
    def test_same_license(self) -> None:
        result = CompatibilityMatrix().is_compatible("MIT", "MIT")
        assert result.verdict == Verdict.SAME

    def test_mit_to_gpl(self) -> None:
        result = CompatibilityMatrix().is_compatible("MIT", "GPL-3.0-only")
        assert result.verdict == Verdict.COMPATIBLE

    def test_gpl_to_mit(self) -> None:
        result = CompatibilityMatrix().is_compatible("GPL-3.0-only", "MIT")
        assert result.verdict == Verdict.INCOMPATIBLE

    def test_unknown_license(self) -> None:
        result = CompatibilityMatrix().is_compatible("NONEXISTENT-LICENSE", "MIT")
        assert result.verdict == Verdict.UNKNOWN

    def test_result_fields(self) -> None:
        result = CompatibilityMatrix().is_compatible("MIT", "Apache-2.0")
        assert result.inbound == "MIT"
        assert result.outbound == "Apache-2.0"


class TestKnownLicenses:
    def test_returns_list(self) -> None:
        licenses = CompatibilityMatrix().known_licenses()
        assert isinstance(licenses, list)
        assert len(licenses) > 50

    def test_contains_common_licenses(self) -> None:
        licenses = CompatibilityMatrix().known_licenses()
        assert "MIT" in licenses
        assert "Apache-2.0" in licenses
        assert "GPL-3.0-only" in licenses


class TestFindCompatibleOutbound:
    def test_permissive_only(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound(
            ["MIT", "BSD-3-Clause"],
        )
        assert "MIT" in compatible
        assert "Apache-2.0" in compatible
        assert "GPL-3.0-only" in compatible

    def test_gpl_restricts(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound(
            ["MIT", "GPL-3.0-only"],
        )
        assert "MIT" not in compatible
        assert "GPL-3.0-only" in compatible

    def test_empty_input(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound([])
        assert len(compatible) > 0


class TestFindIncompatiblePairs:
    def test_no_conflicts_permissive(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            ["MIT", "Apache-2.0", "BSD-3-Clause"],
        )
        assert len(result) == 0

    def test_gpl2_vs_apache2(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            ["GPL-2.0-only", "Apache-2.0"],
        )
        assert len(result) > 0
        assert result[0].verdict == Verdict.INCOMPATIBLE


class TestInstanceIsolation:
    def test_instances_can_share_a_store(self) -> None:
        store = OSADLDataStore()
        a = CompatibilityMatrix(store=store)
        b = CompatibilityMatrix(store=store)
        assert a.known_licenses() == b.known_licenses()

    def test_default_instances_are_independent(self) -> None:
        a = CompatibilityMatrix()
        b = CompatibilityMatrix()
        # Each owns its own default store; neither holds process-wide state.
        assert a is not b
