"""Tests for ExpressionEvaluator (AND/OR-aware SPDX evaluation)."""

from __future__ import annotations

from license_audit.core.models import LicenseCategory
from license_audit.licenses.expression import ExpressionEvaluator


class TestAlternatives:
    def test_single_license(self) -> None:
        assert ExpressionEvaluator().alternatives("MIT") == [["MIT"]]

    def test_simple_and(self) -> None:
        result = ExpressionEvaluator().alternatives("MPL-2.0 AND MIT")
        assert len(result) == 1
        assert sorted(result[0]) == ["MIT", "MPL-2.0"]

    def test_simple_or(self) -> None:
        result = ExpressionEvaluator().alternatives("Apache-2.0 OR MIT")
        assert len(result) == 2
        flat = [r for alt in result for r in alt]
        assert "Apache-2.0" in flat
        assert "MIT" in flat

    def test_nested_and_over_or(self) -> None:
        result = ExpressionEvaluator().alternatives(
            "MPL-2.0 AND (Apache-2.0 OR MIT)",
        )
        assert len(result) == 2
        for alt in result:
            assert "MPL-2.0" in alt
        joined = {tuple(sorted(a)) for a in result}
        assert ("Apache-2.0", "MPL-2.0") in joined
        assert ("MIT", "MPL-2.0") in joined

    def test_or_over_and(self) -> None:
        result = ExpressionEvaluator().alternatives(
            "MIT OR (MPL-2.0 AND BSD-3-Clause)",
        )
        assert len(result) == 2
        sets = {tuple(sorted(a)) for a in result}
        assert ("MIT",) in sets
        assert ("BSD-3-Clause", "MPL-2.0") in sets

    def test_unparseable(self) -> None:
        assert ExpressionEvaluator().alternatives("not a valid expression!!!") == [[]]

    def test_deprecated_ids_normalized(self) -> None:
        result = ExpressionEvaluator().alternatives("GPL-2.0")
        assert result == [["GPL-2.0-only"]]

    def test_with_exception_is_single_component(self) -> None:
        result = ExpressionEvaluator().alternatives(
            "GPL-2.0-only WITH Classpath-exception-2.0 AND MIT",
        )
        assert len(result) == 1
        assert sorted(result[0]) == [
            "GPL-2.0-only WITH Classpath-exception-2.0",
            "MIT",
        ]


class TestRequiredIds:
    def test_single_license(self) -> None:
        assert ExpressionEvaluator().required_ids("MIT") == ["MIT"]

    def test_and_keeps_all_components(self) -> None:
        ids = ExpressionEvaluator().required_ids("MPL-2.0 AND MIT")
        assert sorted(ids) == ["MIT", "MPL-2.0"]

    def test_or_picks_most_permissive(self) -> None:
        assert ExpressionEvaluator().required_ids("GPL-3.0-only OR MIT") == ["MIT"]

    def test_or_picks_lowest_rank_branch(self) -> None:
        assert ExpressionEvaluator().required_ids("MPL-2.0 OR Apache-2.0") == [
            "Apache-2.0",
        ]

    def test_nested_picks_best_branch(self) -> None:
        # Both alternatives tie at weak-copyleft (MPL is in each), so we
        # only assert that MPL-2.0 plus one of Apache/MIT survives.
        ids = ExpressionEvaluator().required_ids("MPL-2.0 AND (Apache-2.0 OR MIT)")
        assert "MPL-2.0" in ids
        assert any(lic in ids for lic in ("Apache-2.0", "MIT"))

    def test_or_over_and_prefers_permissive_branch(self) -> None:
        ids = ExpressionEvaluator().required_ids(
            "MIT OR (MPL-2.0 AND BSD-3-Clause)",
        )
        assert ids == ["MIT"]

    def test_unparseable_returns_empty(self) -> None:
        assert ExpressionEvaluator().required_ids("garbage!!!") == []

    def test_deprecated_id(self) -> None:
        assert ExpressionEvaluator().required_ids("GPL-2.0") == ["GPL-2.0-only"]

    def test_overrides_steer_branch_choice(self) -> None:
        # With MIT deemed proprietary, the GPL branch is now the most
        # permissive alternative, matching what classify() would pick.
        overrides = {"mit": LicenseCategory.PROPRIETARY}
        assert ExpressionEvaluator().required_ids(
            "GPL-3.0-only OR MIT", overrides=overrides
        ) == ["GPL-3.0-only"]


class TestClassify:
    def test_single_permissive(self) -> None:
        assert ExpressionEvaluator().classify("MIT") == LicenseCategory.PERMISSIVE

    def test_single_weak_copyleft(self) -> None:
        assert (
            ExpressionEvaluator().classify("MPL-2.0") == LicenseCategory.WEAK_COPYLEFT
        )

    def test_and_picks_most_restrictive(self) -> None:
        assert (
            ExpressionEvaluator().classify("MPL-2.0 AND MIT")
            == LicenseCategory.WEAK_COPYLEFT
        )

    def test_and_with_strong_copyleft(self) -> None:
        assert (
            ExpressionEvaluator().classify("GPL-3.0-only AND MIT")
            == LicenseCategory.STRONG_COPYLEFT
        )

    def test_or_picks_most_permissive(self) -> None:
        assert (
            ExpressionEvaluator().classify("GPL-3.0-only OR MIT")
            == LicenseCategory.PERMISSIVE
        )

    def test_nested_and_over_or_keeps_restrictive_floor(self) -> None:
        assert (
            ExpressionEvaluator().classify("MPL-2.0 AND (Apache-2.0 OR MIT)")
            == LicenseCategory.WEAK_COPYLEFT
        )

    def test_or_over_and_can_escape_restriction(self) -> None:
        assert (
            ExpressionEvaluator().classify("MIT OR (MPL-2.0 AND BSD-3-Clause)")
            == LicenseCategory.PERMISSIVE
        )

    def test_unparseable_falls_back_to_classifier(self) -> None:
        assert ExpressionEvaluator().classify("garbage!!!") == LicenseCategory.UNKNOWN

    def test_real_world_orjson(self) -> None:
        assert (
            ExpressionEvaluator().classify("MPL-2.0 AND (Apache-2.0 OR MIT)")
            == LicenseCategory.WEAK_COPYLEFT
        )

    def test_real_world_tqdm(self) -> None:
        assert (
            ExpressionEvaluator().classify("MPL-2.0 AND MIT")
            == LicenseCategory.WEAK_COPYLEFT
        )

    def test_unclassified_component_makes_and_unknown(self) -> None:
        assert (
            ExpressionEvaluator().classify("Apache-2.0 AND CNRI-Python")
            == LicenseCategory.UNKNOWN
        )

    def test_override_resolves_unclassified_component(self) -> None:
        assert (
            ExpressionEvaluator().classify(
                "Apache-2.0 AND CNRI-Python",
                overrides={"cnri-python": LicenseCategory.PERMISSIVE},
            )
            == LicenseCategory.PERMISSIVE
        )

    def test_with_exception_uses_matrix_data(self) -> None:
        # The OSADL matrix carries this WITH string as its own entry.
        assert (
            ExpressionEvaluator().classify(
                "GPL-2.0-only WITH Classpath-exception-2.0 AND MIT",
            )
            == LicenseCategory.WEAK_COPYLEFT
        )

    def test_with_exception_falls_back_to_base_license(self) -> None:
        # No OSADL entry for this WITH form, so the Apache-2.0 base
        # sets the category.
        assert (
            ExpressionEvaluator().classify("Apache-2.0 WITH LLVM-exception AND MIT")
            == LicenseCategory.PERMISSIVE
        )

    def test_with_exception_not_flagged_unknown(self) -> None:
        assert (
            ExpressionEvaluator().unknown_components(
                "Apache-2.0 WITH LLVM-exception AND MIT",
            )
            == []
        )

    def test_deemed_with_exception(self) -> None:
        overrides = {"apache-2.0 with llvm-exception": LicenseCategory.PROPRIETARY}
        assert (
            ExpressionEvaluator().classify(
                "Apache-2.0 WITH LLVM-exception AND MIT",
                overrides=overrides,
            )
            == LicenseCategory.PROPRIETARY
        )


class TestPassesDeniedAllowed:
    def test_no_constraints_passes(self) -> None:
        assert ExpressionEvaluator().passes_denied_allowed("MIT", set(), set()) is True

    def test_simple_denied_blocks(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed("MIT", {"mit"}, set()) is False
        )

    def test_or_with_one_denied_branch_passes(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Apache-2.0 OR MIT",
                {"mit"},
                set(),
            )
            is True
        )

    def test_or_with_all_branches_denied_fails(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Apache-2.0 OR MIT",
                {"mit", "apache-2.0"},
                set(),
            )
            is False
        )

    def test_and_with_one_denied_fails(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "MPL-2.0 AND MIT",
                {"mpl-2.0"},
                set(),
            )
            is False
        )

    def test_allowed_constraint(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Apache-2.0 OR MIT",
                set(),
                {"mit"},
            )
            is True
        )

    def test_allowed_excludes_all_branches(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Apache-2.0 OR MIT",
                set(),
                {"bsd-3-clause"},
            )
            is False
        )

    def test_and_must_have_all_in_allowed(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "MPL-2.0 AND MIT",
                set(),
                {"mit"},
            )
            is False
        )

    def test_unparseable_blocked(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "garbage!!!",
                set(),
                {"mit"},
            )
            is False
        )

    def test_denied_base_license_blocks_with_exception(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "GPL-2.0-only WITH Classpath-exception-2.0",
                {"gpl-2.0-only"},
                set(),
            )
            is False
        )

    def test_unparseable_unrelated_to_denylist_passes(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Custom EULA v2 (internal)",
                {"gpl-3.0-only"},
                set(),
            )
            is True
        )

    def test_unparseable_matched_whole_against_denylist(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Custom EULA v2 (internal)",
                {"custom eula v2 (internal)"},
                set(),
            )
            is False
        )
