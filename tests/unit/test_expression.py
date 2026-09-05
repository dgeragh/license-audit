"""Tests for ExpressionEvaluator (AND/OR-aware SPDX evaluation)."""

from __future__ import annotations

from license_audit.core.compatibility import Inbound
from license_audit.core.models import UNKNOWN_LICENSE, LicenseCategory
from license_audit.licenses.expression import (
    ExpressionEvaluator,
    normalize_license_key,
)


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


class TestNormalizeLicenseKey:
    def test_lowercases(self) -> None:
        assert normalize_license_key("MIT") == "mit"

    def test_collapses_internal_whitespace(self) -> None:
        assert normalize_license_key("  Proprietary   License ") == (
            "proprietary license"
        )

    def test_matches_across_spellings(self) -> None:
        assert normalize_license_key("MPL-2.0 AND  MIT") == normalize_license_key(
            "mpl-2.0 and mit"
        )


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


class TestBestAlternatives:
    def test_tied_alternatives_all_kept(self) -> None:
        assert ExpressionEvaluator().best_alternatives("Apache-2.0 OR MIT") == [
            ["Apache-2.0"],
            ["MIT"],
        ]

    def test_higher_rank_alternative_dropped(self) -> None:
        assert ExpressionEvaluator().best_alternatives(
            "MIT OR GPL-3.0-only OR Apache-2.0"
        ) == [["MIT"], ["Apache-2.0"]]

    def test_unparseable_returns_empty(self) -> None:
        assert ExpressionEvaluator().best_alternatives("garbage!!!") == []

    def test_overrides_change_ranking(self) -> None:
        overrides = {"mit": LicenseCategory.PROPRIETARY}
        assert ExpressionEvaluator().best_alternatives(
            "GPL-3.0-only OR MIT", overrides=overrides
        ) == [["GPL-3.0-only"]]


class TestInbound:
    def test_single_license(self) -> None:
        assert ExpressionEvaluator().inbound("MIT") == [Inbound((("MIT",),))]

    def test_and_yields_one_unit_per_component(self) -> None:
        units = ExpressionEvaluator().inbound("MPL-2.0 AND MIT")
        assert [u.label for u in units] == ["MPL-2.0", "MIT"]

    def test_tied_or_is_one_unit(self) -> None:
        assert ExpressionEvaluator().inbound("Apache-2.0 OR MIT") == [
            Inbound((("Apache-2.0",), ("MIT",))),
        ]

    def test_or_contributes_only_best_branch(self) -> None:
        assert ExpressionEvaluator().inbound("GPL-3.0-only OR MIT") == [
            Inbound((("MIT",),)),
        ]

    def test_common_component_factored_out(self) -> None:
        units = ExpressionEvaluator().inbound("MPL-2.0 AND (Apache-2.0 OR MIT)")
        assert [u.label for u in units] == ["MPL-2.0", "Apache-2.0 OR MIT"]

    def test_and_nested_in_or_keeps_joint_requirement(self) -> None:
        units = ExpressionEvaluator().inbound("GPL-2.0-only OR (MIT AND Apache-2.0)")
        assert [u.label for u in units] == ["MIT", "Apache-2.0"]

    def test_unknown_contributes_nothing(self) -> None:
        assert ExpressionEvaluator().inbound(UNKNOWN_LICENSE) == []

    def test_unparseable_contributes_nothing(self) -> None:
        assert ExpressionEvaluator().inbound("garbage!!!") == []

    def test_deprecated_id_promoted(self) -> None:
        assert ExpressionEvaluator().inbound("GPL-2.0")[0].label == "GPL-2.0-only"

    def test_overridden_component_dropped(self) -> None:
        overrides = {"cnri-python": LicenseCategory.PERMISSIVE}
        units = ExpressionEvaluator().inbound("Apache-2.0 AND CNRI-Python", overrides)
        assert [u.label for u in units] == ["Apache-2.0"]

    def test_overridden_whole_expression_contributes_nothing(self) -> None:
        overrides = {"gpl-2.0-only and gpl-3.0-only": LicenseCategory.PERMISSIVE}
        assert (
            ExpressionEvaluator().inbound("GPL-2.0-only AND GPL-3.0-only", overrides)
            == []
        )

    def test_override_steers_branch_and_keeps_its_ids(self) -> None:
        # MIT deemed proprietary leaves GPL as the best branch; its id still counts.
        overrides = {"mit": LicenseCategory.PROPRIETARY}
        assert ExpressionEvaluator().inbound("GPL-3.0-only OR MIT", overrides) == [
            Inbound((("GPL-3.0-only",),)),
        ]

    def test_override_emptying_a_branch_lifts_the_constraint(self) -> None:
        overrides = {"foo-1.0": LicenseCategory.PERMISSIVE}
        assert ExpressionEvaluator().inbound("GPL-3.0-only OR Foo-1.0", overrides) == []


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

    def test_allowed_base_license_admits_with_exception(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "Apache-2.0 WITH LLVM-exception",
                set(),
                {"apache-2.0"},
            )
            is True
        )

    def test_allowed_exact_with_form_still_accepted(self) -> None:
        assert (
            ExpressionEvaluator().passes_denied_allowed(
                "GPL-2.0-only WITH Classpath-exception-2.0",
                set(),
                {"gpl-2.0-only with classpath-exception-2.0"},
            )
            is True
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
