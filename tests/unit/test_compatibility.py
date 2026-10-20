"""Tests for CompatibilityMatrix."""

from __future__ import annotations

from license_audit._data import OSADLDataStore
from license_audit.core.compatibility import CompatibilityMatrix, Inbound
from license_audit.core.models import Verdict


def _inbound(*ids: str) -> list[Inbound]:
    return [Inbound(((lic,),)) for lic in ids]


class TestInboundLabel:
    def test_single_id(self) -> None:
        assert Inbound((("MIT",),)).label == "MIT"

    def test_and_joins_components(self) -> None:
        assert Inbound((("MPL-2.0", "MIT"),)).label == "MPL-2.0 AND MIT"

    def test_or_groups_compound_alternatives(self) -> None:
        unit = Inbound((("MPL-2.0", "Apache-2.0"), ("MIT",)))
        assert unit.label == "(MPL-2.0 AND Apache-2.0) OR MIT"


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
            _inbound("MIT", "BSD-3-Clause"),
        )
        assert "MIT" in compatible
        assert "Apache-2.0" in compatible
        assert "GPL-3.0-only" in compatible

    def test_gpl_restricts(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound(
            _inbound("MIT", "GPL-3.0-only"),
        )
        assert "MIT" not in compatible
        assert "GPL-3.0-only" in compatible

    def test_empty_input(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound([])
        assert len(compatible) > 0

    def test_unknown_id_imposes_nothing(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound(
            _inbound("MIT", "NONEXISTENT-LICENSE"),
        )
        assert "MIT" in compatible

    def test_any_alternative_satisfies(self) -> None:
        # Apache-2.0 alone rules out GPL-2.0-only; the BSD branch admits it.
        dual = Inbound((("Apache-2.0",), ("BSD-2-Clause",)))
        compatible = CompatibilityMatrix().find_compatible_outbound(
            [dual, *_inbound("GPL-2.0-only")],
        )
        assert "GPL-2.0-only" in compatible

    def test_compound_alternative_requires_all_its_ids(self) -> None:
        unit = Inbound((("MIT", "GPL-3.0-only"),))
        compatible = CompatibilityMatrix().find_compatible_outbound([unit])
        assert "MIT" not in compatible
        assert "GPL-3.0-only" in compatible


class TestFindIncompatiblePairs:
    def test_no_conflicts_permissive(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("MIT", "Apache-2.0", "BSD-3-Clause"),
        )
        assert len(result) == 0

    def test_gpl2_vs_apache2(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("GPL-2.0-only", "Apache-2.0"),
        )
        assert len(result) > 0
        assert {result[0].license_a, result[0].license_b} == {
            "GPL-2.0-only",
            "Apache-2.0",
        }

    def test_duplicate_units_checked_once(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("GPL-2.0-only", "Apache-2.0", "Apache-2.0"),
        )
        assert len(result) == 1

    def test_unknown_id_never_conflicts(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("GPL-2.0-only", "NONEXISTENT-LICENSE"),
        )
        assert result == []

    def test_dual_license_with_one_clean_branch_is_not_flagged(self) -> None:
        # packaging and cryptography declare "Apache-2.0 OR BSD-x-Clause".
        dual = Inbound((("Apache-2.0",), ("BSD-2-Clause",)))
        result = CompatibilityMatrix().find_incompatible_pairs(
            [dual, *_inbound("GPL-2.0-only")],
        )
        assert result == []

    def test_dual_license_named_whole_when_every_branch_conflicts(self) -> None:
        dual = Inbound((("Apache-2.0",), ("GPL-3.0-only",)))
        result = CompatibilityMatrix().find_incompatible_pairs(
            [dual, *_inbound("GPL-2.0-only")],
        )
        assert [(p.license_a, p.license_b) for p in result] == [
            ("Apache-2.0 OR GPL-3.0-only", "GPL-2.0-only"),
        ]


class TestLibraryScope:
    """Permissive and weak-copyleft obligations stay with the dependency's own
    files; only strong copyleft reaches the combined work."""

    def test_weak_copyleft_leaves_permissive_outbound_open(self) -> None:
        compatible = CompatibilityMatrix().find_compatible_outbound(
            _inbound("MPL-2.0", "MIT"),
        )
        assert "MIT" in compatible
        assert "Apache-2.0" in compatible

    def test_weak_copyleft_and_permissive_never_conflict(self) -> None:
        # certifi (MPL-2.0) and typing-extensions (PSF-2.0) sit in most trees.
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("MPL-2.0", "PSF-2.0", "LGPL-2.1-only", "Apache-2.0"),
        )
        assert result == []

    def test_strong_copyleft_still_binds_weak_copyleft(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("GPL-2.0-only", "EPL-2.0"),
        )
        assert len(result) == 1

    def test_strong_copyleft_needs_copyleft_outbound(self) -> None:
        # OSADL lets the weak-copyleft Classpath variant take in GPL-2.0-only
        # code, but the combined work is then GPL-2.0-only, which rules out
        # Apache-2.0.
        compatible = CompatibilityMatrix().find_compatible_outbound(
            _inbound("GPL-2.0-only", "Apache-2.0"),
        )
        assert compatible == []


class TestPsfCorrection:
    def test_psf_usable_in_gpl_family_works(self) -> None:
        matrix = CompatibilityMatrix()
        assert matrix.raw_verdict("GPL-2.0-only", "PSF-2.0") == "Yes"
        assert matrix.raw_verdict("GPL-3.0-or-later", "PSF-2.0") == "Yes"
        assert matrix.raw_verdict("AGPL-3.0-only", "PSF-2.0") == "Yes"

    def test_psf_and_gpl_dependencies_do_not_conflict(self) -> None:
        result = CompatibilityMatrix().find_incompatible_pairs(
            _inbound("PSF-2.0", "GPL-3.0-or-later"),
        )
        assert result == []

    def test_other_verdicts_untouched(self) -> None:
        assert CompatibilityMatrix().raw_verdict("GPL-2.0-only", "Apache-2.0") == "No"


class _StubStore(OSADLDataStore):
    def __init__(self, matrix: dict[str, dict[str, str]]) -> None:
        super().__init__()
        self._matrix = matrix


class TestCheckDependencyVerdict:
    """'Check dependency' is lenient for pair detection but excluded from
    recommendations: the tool must not suggest an outbound license OSADL
    flags for review."""

    # The only common outbound for A+B goes through a "Check dependency"
    # cell, so pair detection and recommendation diverge on it.
    _MATRIX: dict[str, dict[str, str]] = {
        "Lic-A": {"Lic-A": "Same", "Lic-B": "Check dependency"},
        "Lic-B": {"Lic-A": "No", "Lic-B": "Same"},
    }

    def test_excluded_from_recommendations(self) -> None:
        matrix = CompatibilityMatrix(store=_StubStore(self._MATRIX))
        assert matrix.find_compatible_outbound(_inbound("Lic-A", "Lic-B")) == []

    def test_still_counts_for_pair_detection(self) -> None:
        matrix = CompatibilityMatrix(store=_StubStore(self._MATRIX))
        assert matrix.find_incompatible_pairs(_inbound("Lic-A", "Lic-B")) == []

    def test_clean_cells_still_recommended(self) -> None:
        matrix = CompatibilityMatrix(store=_StubStore(self._MATRIX))
        assert matrix.find_compatible_outbound(_inbound("Lic-A")) == ["Lic-A"]


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
