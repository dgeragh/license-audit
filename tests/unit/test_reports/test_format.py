"""Tests for shared report formatters."""

from __future__ import annotations

from license_audit.core.models import (
    ActionItem,
    AnalysisReport,
    CompatibilityResult,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
    Verdict,
)
from license_audit.reports._format import (
    ActionItemFormatter,
    IncompatiblePairFormatter,
    NoRecommendationReason,
    SummaryStats,
    category_label,
    explain_no_recommendation,
    fenced_code_block,
    license_label,
    markdown_license_cell,
)


class TestSummaryStats:
    def test_classified_permissive_counts_as_permissive_not_unknown(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="gpu",
                    version="1.0",
                    license_expression="UNKNOWN",
                    declared_license="Proprietary License",
                    category=LicenseCategory.PERMISSIVE,
                    category_overridden=True,
                )
            ],
        )
        stats = SummaryStats.from_report(report)
        assert stats.permissive == 1
        assert stats.unknown == 0

    def test_classified_copyleft_counts_as_copyleft(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="x",
                    version="1.0",
                    license_expression="UNKNOWN",
                    declared_license="Some Copyleft EULA",
                    category=LicenseCategory.STRONG_COPYLEFT,
                    category_overridden=True,
                )
            ],
        )
        stats = SummaryStats.from_report(report)
        assert stats.copyleft == 1
        assert stats.unknown == 0

    def test_ignored_package_not_double_counted(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="gpl",
                    version="1.0",
                    license_expression="GPL-3.0-only",
                    category=LicenseCategory.STRONG_COPYLEFT,
                    ignored=True,
                ),
                PackageLicense(
                    name="mit",
                    version="1.0",
                    license_expression="MIT",
                    category=LicenseCategory.PERMISSIVE,
                ),
            ],
        )
        stats = SummaryStats.from_report(report)
        assert stats.ignored == 1
        assert stats.copyleft == 0  # the ignored GPL package is not also copyleft
        assert stats.permissive == 1

    def test_proprietary_counted_separately(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="x",
                    version="1.0",
                    license_expression="UNKNOWN",
                    declared_license="Proprietary License",
                    category=LicenseCategory.PROPRIETARY,
                    category_overridden=True,
                )
            ],
        )
        stats = SummaryStats.from_report(report)
        assert stats.proprietary == 1
        assert stats.unknown == 0


class TestCategoryLabel:
    def _pkg(self, **kw: object) -> PackageLicense:
        base = {
            "name": "p",
            "version": "1.0",
            "license_source": LicenseSource.METADATA,
        }
        base.update(kw)
        return PackageLicense(**base)  # type: ignore[arg-type]

    def test_plain_category(self) -> None:
        pkg = self._pkg(category=LicenseCategory.PERMISSIVE)
        assert category_label(pkg) == "permissive"

    def test_ignored_suffix(self) -> None:
        pkg = self._pkg(category=LicenseCategory.STRONG_COPYLEFT, ignored=True)
        assert category_label(pkg) == "strong-copyleft (ignored)"

    def test_classified_suffix(self) -> None:
        pkg = self._pkg(category=LicenseCategory.PERMISSIVE, category_overridden=True)
        assert category_label(pkg) == "permissive (classified)"

    def test_classified_suffix_is_category_neutral(self) -> None:
        pkg = self._pkg(
            category=LicenseCategory.STRONG_COPYLEFT, category_overridden=True
        )
        assert category_label(pkg) == "strong-copyleft (classified)"

    def test_ignored_takes_precedence_over_classified(self) -> None:
        pkg = self._pkg(
            category=LicenseCategory.PERMISSIVE,
            category_overridden=True,
            ignored=True,
        )
        assert category_label(pkg) == "permissive (ignored)"


class TestLicenseLabel:
    def test_short_value_unchanged(self) -> None:
        assert license_label("BSD-3-Clause") == "BSD-3-Clause"

    def test_collapses_internal_whitespace_and_newlines(self) -> None:
        assert license_label("\n  Proprietary\tLicense") == ("Proprietary License")

    def test_truncates_overlong_value(self) -> None:
        result = license_label("x" * 500, limit=40)
        assert len(result) == 40
        assert result.endswith("...")

    def test_default_limit_is_120(self) -> None:
        # Pins the production default used by every table/notices call site.
        result = license_label("x" * 200)
        assert len(result) == 120
        assert result.endswith("...")


class TestFencedCodeBlock:
    def test_plain_text_uses_three_backticks(self) -> None:
        block = fenced_code_block("just a license\nno fences")
        assert block.startswith("```\n")
        assert not block.startswith("````")
        assert block.endswith("\n```")

    def test_embedded_fence_widens_the_outer_fence(self) -> None:
        # An embedded ``` must not prematurely close the block.
        block = fenced_code_block("LICENSE\n```\nbreakout\n```\nmore")
        assert block.startswith("````\n")
        assert block.endswith("\n````")
        assert "breakout" in block

    def test_outer_fence_longer_than_longest_run(self) -> None:
        block = fenced_code_block("a ```` b")  # 4-backtick run in body
        assert block.startswith("`````\n")  # needs 5


class TestMarkdownLicenseCell:
    def test_escapes_pipes_to_protect_table(self) -> None:
        # A pipe in a declared license would otherwise add phantom columns.
        assert markdown_license_cell("Foo | Bar License") == "Foo \\| Bar License"

    def test_clean_expression_passes_through(self) -> None:
        assert markdown_license_cell("Apache-2.0 OR MIT") == "Apache-2.0 OR MIT"


class TestActionItemFormatterRich:
    def test_warning_uses_yellow(self) -> None:
        item = ActionItem(severity="warning", message="watch out")
        result = ActionItemFormatter.rich(item)
        assert "[yellow]" in result
        assert "watch out" in result

    def test_error_uses_red(self) -> None:
        item = ActionItem(severity="error", message="nope")
        result = ActionItemFormatter.rich(item)
        assert "[red]" in result
        assert "nope" in result

    def test_message_is_escaped(self) -> None:
        """Rich markup characters in the message are escaped to avoid
        accidentally styling user-supplied text."""
        item = ActionItem(severity="warning", message="[x] not markup")
        result = ActionItemFormatter.rich(item)
        # Escaped form prefixes open-brackets with a backslash.
        assert r"\[x]" in result


class TestActionItemFormatterMarkdown:
    def test_warning_label(self) -> None:
        item = ActionItem(severity="warning", message="heads up")
        result = ActionItemFormatter.markdown(item)
        assert result.startswith("- [Warning]")
        assert "heads up" in result

    def test_error_label(self) -> None:
        item = ActionItem(severity="error", message="broken")
        result = ActionItemFormatter.markdown(item)
        assert result.startswith("- [Error]")

    def test_package_prefix_when_set(self) -> None:
        item = ActionItem(severity="error", package="foo", message="x")
        assert "**foo**: x" in ActionItemFormatter.markdown(item)

    def test_no_prefix_when_package_empty(self) -> None:
        item = ActionItem(severity="error", message="x")
        assert "**" not in ActionItemFormatter.markdown(item)


class TestIncompatiblePairFormatter:
    def _pair(self) -> CompatibilityResult:
        return CompatibilityResult(
            inbound="GPL-2.0-only",
            outbound="Apache-2.0",
            verdict=Verdict.INCOMPATIBLE,
        )

    def test_rich(self) -> None:
        result = IncompatiblePairFormatter.rich(self._pair())
        assert "[red]" in result
        assert "GPL-2.0-only" in result
        assert "Apache-2.0" in result

    def test_markdown_row(self) -> None:
        result = IncompatiblePairFormatter.markdown_row(self._pair())
        assert result == "| GPL-2.0-only | Apache-2.0 | incompatible |"


class TestExplainNoRecommendation:
    def test_none_when_recommendations_exist(self) -> None:
        report = AnalysisReport(recommended_licenses=["MIT"])
        assert explain_no_recommendation(report) is None

    def test_unknown_branch(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="mystery",
                    version="1.0",
                    category=LicenseCategory.UNKNOWN,
                )
            ],
        )
        explanation = explain_no_recommendation(report)
        assert explanation is not None
        assert explanation.reason is NoRecommendationReason.UNKNOWN_LICENSES
        assert explanation.headline == "Cannot recommend a license"
        assert "mystery" in explanation.detail

    def test_deemed_branch(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="vendor-sdk",
                    version="1.0",
                    category=LicenseCategory.STRONG_COPYLEFT,
                    category_overridden=True,
                )
            ],
        )
        explanation = explain_no_recommendation(report)
        assert explanation is not None
        assert explanation.reason is NoRecommendationReason.DEEMED_CONSTRAINT
        assert explanation.headline == "Cannot recommend a license"
        assert "outbound compatibility can't be computed" in explanation.detail
        assert "vendor-sdk" in explanation.detail

    def test_conflict_branch(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="gpl-pkg",
                    version="1.0",
                    license_expression="GPL-3.0-only",
                    category=LicenseCategory.STRONG_COPYLEFT,
                )
            ],
        )
        explanation = explain_no_recommendation(report)
        assert explanation is not None
        assert explanation.reason is NoRecommendationReason.NO_COMMON_LICENSE
        assert explanation.headline == "No compatible outbound license found"
        assert "override" in explanation.detail

    def test_unknown_wins_over_deemed(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="mystery",
                    version="1.0",
                    category=LicenseCategory.UNKNOWN,
                ),
                PackageLicense(
                    name="vendor-sdk",
                    version="1.0",
                    category=LicenseCategory.STRONG_COPYLEFT,
                    category_overridden=True,
                ),
            ],
        )
        explanation = explain_no_recommendation(report)
        assert explanation is not None
        assert explanation.reason is NoRecommendationReason.UNKNOWN_LICENSES

    def test_ignored_unknown_excluded(self) -> None:
        report = AnalysisReport(
            packages=[
                PackageLicense(
                    name="ignored-unknown",
                    version="1.0",
                    category=LicenseCategory.UNKNOWN,
                    ignored=True,
                    ignore_reason="reviewed",
                )
            ],
        )
        explanation = explain_no_recommendation(report)
        assert explanation is not None
        assert explanation.reason is NoRecommendationReason.NO_COMMON_LICENSE
