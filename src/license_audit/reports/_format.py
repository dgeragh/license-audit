"""Shared helpers for renderer output: stats, headers, footers, and formatters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from rich.markup import escape

from license_audit.core.models import (
    ActionItem,
    AnalysisReport,
    CompatibilityResult,
    LicenseCategory,
    PackageLicense,
)

_ATTRIBUTION_LINK = "[license_audit](https://github.com/dgeragh/license-audit)"
_COPYLEFT_CATEGORIES: frozenset[LicenseCategory] = frozenset({
    LicenseCategory.STRONG_COPYLEFT,
    LicenseCategory.WEAK_COPYLEFT,
    LicenseCategory.NETWORK_COPYLEFT,
})


@dataclass(frozen=True)
class SummaryStats:
    """Aggregate counts derived from an AnalysisReport for summary sections."""

    total: int
    permissive: int
    copyleft: int
    unknown: int
    proprietary: int
    ignored: int

    @classmethod
    def from_report(cls, report: AnalysisReport) -> SummaryStats:
        permissive = 0
        copyleft = 0
        unknown = 0
        proprietary = 0
        ignored = 0
        for pkg in report.packages:
            if pkg.ignored:
                ignored += 1
            elif pkg.category == LicenseCategory.PERMISSIVE:
                permissive += 1
            elif pkg.category in _COPYLEFT_CATEGORIES:
                copyleft += 1
            elif pkg.category == LicenseCategory.PROPRIETARY:
                proprietary += 1
            else:
                unknown += 1
        return cls(
            total=len(report.packages),
            permissive=permissive,
            copyleft=copyleft,
            unknown=unknown,
            proprietary=proprietary,
            ignored=ignored,
        )


def category_label(pkg: PackageLicense) -> str:
    """Category value, annotated when it was ignored or user-classified."""
    if pkg.ignored:
        return f"{pkg.category.value} (ignored)"
    if pkg.category_overridden:
        return f"{pkg.category.value} (classified)"
    return pkg.category.value


def deemed_constraint_packages(report: AnalysisReport) -> list[PackageLicense]:
    """Active packages the user classified as a non-permissive category."""
    return [
        p
        for p in report.packages
        if not p.ignored
        and p.category_overridden
        and p.category != LicenseCategory.PERMISSIVE
    ]


class NoRecommendationReason(StrEnum):
    """Why a report has no recommended licenses."""

    UNKNOWN_LICENSES = "unknown-licenses"
    DEEMED_CONSTRAINT = "deemed-constraint"
    NO_COMMON_LICENSE = "no-common-license"


@dataclass(frozen=True)
class NoRecommendationExplanation:
    """Renderer-neutral plain-text explanation for withheld recommendations."""

    reason: NoRecommendationReason
    headline: str
    detail: str


def explain_no_recommendation(
    report: AnalysisReport,
) -> NoRecommendationExplanation | None:
    """Explain why `report` has no recommended licenses, or None if it does."""
    if report.recommended_licenses:
        return None

    unknown = [
        p
        for p in report.packages
        if not p.ignored and p.category == LicenseCategory.UNKNOWN
    ]
    if unknown:
        names = ", ".join(p.name for p in unknown)
        return NoRecommendationExplanation(
            reason=NoRecommendationReason.UNKNOWN_LICENSES,
            headline="Cannot recommend a license",
            detail=(
                f"{len(unknown)} dependency(ies) have an unclassified license "
                f"({names}). Resolve them via "
                "[tool.license-audit.license-classifications] or "
                "[tool.license-audit.overrides] and re-run."
            ),
        )

    deemed = deemed_constraint_packages(report)
    if deemed:
        names = ", ".join(p.name for p in deemed)
        return NoRecommendationExplanation(
            reason=NoRecommendationReason.DEEMED_CONSTRAINT,
            headline="Cannot recommend a license",
            detail=(
                f"{len(deemed)} dependency(ies) are classified as non-permissive "
                f"({names}) and excluded from compatibility analysis, so outbound "
                "compatibility can't be computed. Remove the classification, or "
                "assert a genuine SPDX license via [tool.license-audit.overrides], "
                "if you need recommendations."
            ),
        )

    return NoRecommendationExplanation(
        reason=NoRecommendationReason.NO_COMMON_LICENSE,
        headline="No compatible outbound license found",
        detail=(
            "Your dependencies have conflicting license requirements. Add an "
            "override in [tool.license-audit.overrides] if a detected license "
            "is incorrect, or replace a conflicting dependency."
        ),
    )


def license_label(value: str, limit: int = 120) -> str:
    """Collapse whitespace and bound length so a license fits one table cell."""
    collapsed = " ".join(value.split())
    if len(collapsed) > limit:
        return collapsed[: limit - 3].rstrip() + "..."
    return collapsed


def markdown_license_cell(value: str) -> str:
    """`license_label` plus pipe-escaping for safe markdown-table inclusion."""
    return license_label(value).replace("|", "\\|")


def fenced_code_block(text: str) -> str:
    """Wrap `text` in a backtick fence long enough to contain it intact."""
    longest = 0
    run = 0
    for char in text:
        if char == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text.rstrip()}\n{fence}"


def generated_metadata_block(report: AnalysisReport) -> str:
    """`Generated: <timestamp>` line plus an optional `Source: ...` line."""
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    source_line = f"Source: {report.source}\n" if report.source else ""
    return f"Generated: {now}\n{source_line}"


def attribution_footer(disclaimer: str) -> str:
    """Trailing attribution block shared by markdown-style renderers."""
    return f"\n---\n\n*Generated by {_ATTRIBUTION_LINK}. {disclaimer}*\n"


class ActionItemFormatter:
    """Formats ActionItems for terminal and markdown output."""

    WARNING_ICON = "\\[!]"
    ERROR_ICON = "\\[x]"
    WARNING_COLOR = "yellow"
    ERROR_COLOR = "red"

    @classmethod
    def rich(cls, item: ActionItem) -> str:
        """Rich-markup line suitable for `console.print`."""
        icon = cls.WARNING_ICON if item.severity == "warning" else cls.ERROR_ICON
        color = cls.WARNING_COLOR if item.severity == "warning" else cls.ERROR_COLOR
        return f"  [{color}]{icon}[/{color}] {escape(item.message)}"

    @classmethod
    def markdown(cls, item: ActionItem) -> str:
        """Single-line markdown bullet."""
        label = "Warning" if item.severity == "warning" else "Error"
        prefix = f"**{item.package}**: " if item.package else ""
        return f"- [{label}] {prefix}{item.message}"


class IncompatiblePairFormatter:
    """Formats incompatible license pairs for terminal and markdown output."""

    ICON = "\\[x]"
    COLOR = "red"

    @classmethod
    def rich(cls, pair: CompatibilityResult) -> str:
        """Rich-markup line for `console.print`."""
        return (
            f"  [{cls.COLOR}]{cls.ICON}[/{cls.COLOR}] "
            f"{pair.inbound} <-> {pair.outbound}"
        )

    @classmethod
    def markdown_row(cls, pair: CompatibilityResult) -> str:
        """Markdown table row for a compatibility table."""
        return f"| {pair.inbound} | {pair.outbound} | {pair.verdict.value} |"
