"""Tests for LicenseRecommender."""

from __future__ import annotations

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


class TestResolveInboundAstDispatch:
    def test_or_resolves_to_single_license(self) -> None:
        resolved = LicenseRecommender().resolve_inbound(["MIT OR GPL-3.0-only"])
        assert resolved == ["MIT"]

    def test_and_resolves_to_all_components(self) -> None:
        resolved = LicenseRecommender().resolve_inbound(["MIT AND BSD-3-Clause"])
        assert set(resolved) == {"MIT", "BSD-3-Clause"}

    def test_unknown_is_skipped(self) -> None:
        assert LicenseRecommender().resolve_inbound(["UNKNOWN"]) == []

    def test_or_nested_in_and_keeps_required_components(self) -> None:
        """AND components outside the OR stay required; the OR resolves to
        its most permissive branch, matching the compatibility check."""
        resolved = LicenseRecommender().resolve_inbound([
            "MIT AND (GPL-3.0-only OR Apache-2.0)"
        ])
        assert set(resolved) == {"MIT", "Apache-2.0"}

    def test_and_nested_in_or_keeps_joint_requirement(self) -> None:
        resolved = LicenseRecommender().resolve_inbound([
            "GPL-2.0-only OR (MIT AND Apache-2.0)"
        ])
        assert set(resolved) == {"MIT", "Apache-2.0"}


class TestRecommendCompoundExpressions:
    def test_or_nested_in_and_recommends_permissive(self) -> None:
        # Pre-fix, the OR branch was resolved from all symbols at once and
        # GPL-3.0-only led the list with MIT missing entirely. GPL stays
        # valid as a more restrictive outbound, just no longer first.
        result = LicenseRecommender().recommend([
            "MIT AND (GPL-3.0-only OR Apache-2.0)"
        ])
        assert result[0] == "MIT"
        assert result.index("MIT") < result.index("GPL-3.0-only")

    def test_and_nested_in_or_excludes_incompatible_outbound(self) -> None:
        # GPL-2.0-only is incompatible with Apache-2.0 per OSADL, so it
        # must not be recommended once the AND branch is chosen.
        result = LicenseRecommender().recommend([
            "GPL-2.0-only OR (MIT AND Apache-2.0)"
        ])
        assert "MIT" in result
        assert "GPL-2.0-only" not in result


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
