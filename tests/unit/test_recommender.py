"""Tests for LicenseRecommender."""

from __future__ import annotations

from license_audit.core.compatibility import Inbound
from license_audit.core.models import LicenseCategory
from license_audit.core.recommender import LicenseRecommender


class TestRecommend:
    def test_permissive_deps(self) -> None:
        result = LicenseRecommender().recommend(
            ["MIT", "Apache-2.0", "BSD-3-Clause"],
        )
        assert len(result) > 0
        assert "MIT" in result

    def test_curated_picks_beat_alphabetical(self) -> None:
        """Mainstream picks (MIT, Apache-2.0) should appear before
        alphabetically-earlier permissive licenses (Apache-1.0)."""
        result = LicenseRecommender().recommend(["MIT"])
        assert "MIT" in result
        assert "Apache-1.0" in result
        assert result.index("MIT") < result.index("Apache-1.0")
        assert result.index("Apache-2.0") < result.index("Apache-1.0")

    def test_curated_order_within_permissive(self) -> None:
        result = LicenseRecommender().recommend(["MIT"])
        assert result.index("MIT") < result.index("Apache-2.0")
        assert result.index("Apache-2.0") < result.index("BSD-2-Clause")

    def test_gpl_dep_restricts(self) -> None:
        result = LicenseRecommender().recommend(["MIT", "GPL-3.0-only"])
        assert "MIT" not in result
        assert "GPL-3.0-only" in result

    def test_empty_deps(self) -> None:
        result = LicenseRecommender().recommend([])
        assert len(result) > 0

    def test_unknown_skipped(self) -> None:
        result = LicenseRecommender().recommend(["MIT", "UNKNOWN"])
        assert len(result) > 0

    def test_or_expression_picks_most_permissive(self) -> None:
        result = LicenseRecommender().recommend(["MIT OR GPL-3.0-only"])
        # OR should reduce to the most permissive alternative (MIT),
        # keeping MIT viable as an outbound license.
        assert "MIT" in result

    def test_and_expression_requires_all(self) -> None:
        result = LicenseRecommender().recommend(["MIT AND BSD-3-Clause"])
        assert len(result) > 0
        assert "MIT" in result

    def test_tied_or_alternatives_both_count(self) -> None:
        # Apache-first ordering must not hide the BSD branch that admits GPL-2.0.
        result = LicenseRecommender().recommend(
            ["Apache-2.0 OR BSD-2-Clause", "GPL-2.0-only"]
        )
        assert "GPL-2.0-only" in result


class TestRecommendWithOverrides:
    _DEEMED = {"cnri-python": LicenseCategory.PERMISSIVE}

    def test_classified_component_is_waived(self) -> None:
        result = LicenseRecommender().recommend(
            ["Apache-2.0 AND CNRI-Python"], self._DEEMED
        )
        assert "MIT" in result

    def test_sibling_component_still_constrains(self) -> None:
        # Apache-2.0 rules out GPL-2.0-only even though CNRI-Python is waived.
        result = LicenseRecommender().recommend(
            ["Apache-2.0 AND CNRI-Python"], self._DEEMED
        )
        assert "GPL-2.0-only" not in result

    def test_sibling_conflict_with_other_dependency_empties_result(self) -> None:
        result = LicenseRecommender().recommend(
            ["Apache-2.0 AND CNRI-Python", "GPL-2.0-only"], self._DEEMED
        )
        assert result == []


class TestResolveInboundAstDispatch:
    def test_or_keeps_every_branch(self) -> None:
        resolved = LicenseRecommender().resolve_inbound(["MIT OR GPL-3.0-only"])
        assert resolved == [Inbound((("MIT",), ("GPL-3.0-only",)))]

    def test_and_resolves_to_all_components(self) -> None:
        resolved = LicenseRecommender().resolve_inbound(["MIT AND BSD-3-Clause"])
        assert {u.label for u in resolved} == {"MIT", "BSD-3-Clause"}

    def test_unknown_is_skipped(self) -> None:
        assert LicenseRecommender().resolve_inbound(["UNKNOWN"]) == []

    def test_or_nested_in_and_keeps_required_components(self) -> None:
        """AND components outside the OR stay required; the OR stays one
        unit with both branches, matching the compatibility check."""
        resolved = LicenseRecommender().resolve_inbound(
            ["MIT AND (GPL-3.0-only OR Apache-2.0)"]
        )
        assert {u.label for u in resolved} == {"MIT", "GPL-3.0-only OR Apache-2.0"}

    def test_and_nested_in_or_keeps_joint_requirement(self) -> None:
        resolved = LicenseRecommender().resolve_inbound(
            ["GPL-2.0-only OR (MIT AND Apache-2.0)"]
        )
        assert {u.label for u in resolved} == {"GPL-2.0-only OR (MIT AND Apache-2.0)"}

    def test_tied_or_stays_one_unit(self) -> None:
        resolved = LicenseRecommender().resolve_inbound(["Apache-2.0 OR MIT"])
        assert resolved == [Inbound((("Apache-2.0",), ("MIT",)))]


class TestRecommendCompoundExpressions:
    def test_or_nested_in_and_recommends_permissive(self) -> None:
        # Pre-fix, the OR branch was resolved from all symbols at once and
        # GPL-3.0-only led the list with MIT missing entirely. GPL stays
        # valid as a more restrictive outbound, just no longer first.
        result = LicenseRecommender().recommend(
            ["MIT AND (GPL-3.0-only OR Apache-2.0)"]
        )
        assert result[0] == "MIT"
        assert result.index("MIT") < result.index("GPL-3.0-only")

    def test_and_nested_in_or_admits_outbound_through_either_branch(self) -> None:
        # GPL-2.0-only can't take the MIT AND Apache-2.0 branch (Apache-2.0 is
        # GPLv2-incompatible), but it can use the GPL-2.0-only branch.
        result = LicenseRecommender().recommend(
            ["GPL-2.0-only OR (MIT AND Apache-2.0)"]
        )
        assert result[0] == "MIT"
        assert "GPL-2.0-only" in result

    def test_less_permissive_branch_resolves_conflict(self) -> None:
        # Using the dual-licensed dependency under GPL-2.0-only fits a
        # GPL-2.0-only project; its Apache-2.0 branch alone would not.
        result = LicenseRecommender().recommend(
            ["Apache-2.0 OR GPL-2.0-only", "GPL-2.0-only"]
        )
        assert result == ["GPL-2.0-only"]


class TestFindMinimum:
    def test_permissive(self) -> None:
        result = LicenseRecommender().find_minimum(["MIT", "BSD-3-Clause"])
        assert result is not None

    def test_gpl(self) -> None:
        result = LicenseRecommender().find_minimum(["MIT", "GPL-3.0-only"])
        assert result is not None
        assert result != "MIT"

    def test_empty(self) -> None:
        result = LicenseRecommender().find_minimum([])
        assert result is not None


class TestReview:
    def test_check_dependency_only_fit_needs_review(self) -> None:
        # OSADL: GPL-2.0-only takes in LGPL-2.1 code only after review.
        recommender = LicenseRecommender()
        deps = ["GPL-2.0-only", "LGPL-2.1-only"]
        assert recommender.recommend(deps) == []
        assert recommender.review(deps) == ["GPL-2.0-only"]

    def test_most_permissive_first(self) -> None:
        review = LicenseRecommender().review(["AGPL-3.0-only", "GPL-3.0-or-later"])
        assert review[0] == "GPL-3.0-only"
        assert "AGPL-3.0-only" in review

    def test_nothing_without_constraints(self) -> None:
        assert LicenseRecommender().review([]) == []

    def test_definite_fits_are_not_repeated(self) -> None:
        recommender = LicenseRecommender()
        deps = ["LGPL-2.1-only", "MIT"]
        assert not set(recommender.review(deps)) & set(recommender.recommend(deps))
