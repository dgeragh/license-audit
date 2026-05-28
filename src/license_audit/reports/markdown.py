"""Markdown compliance report renderer."""

from __future__ import annotations

from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import AnalysisReport, LicenseCategory
from license_audit.reports._format import (
    ActionItemFormatter,
    IncompatiblePairFormatter,
    SummaryStats,
    attribution_footer,
    fenced_code_block,
    generated_metadata_block,
    license_label,
    markdown_license_cell,
)


class MarkdownRenderer:
    """Renders a report as a Markdown compliance document."""

    def __init__(self, classifier: LicenseClassifier | None = None) -> None:
        self._classifier = classifier or LicenseClassifier()

    def render(self, report: AnalysisReport) -> str:
        """Render the report as Markdown."""
        sections = [
            self._header(report),
            self._summary(report),
            self._dependency_table(report),
            self._ignored_packages(report),
            self._classification_breakdown(report),
            self._compatibility_analysis(report),
            self._recommendations(report),
            self._action_items(report),
            self._licenses_requiring_review(report),
            self._footer(),
        ]
        return "\n".join(s for s in sections if s)

    def _header(self, report: AnalysisReport) -> str:
        return (
            f"# License Compliance Report: {report.project_name}\n\n"
            f"{generated_metadata_block(report)}"
        )

    def _summary(self, report: AnalysisReport) -> str:
        stats = SummaryStats.from_report(report)
        status = "PASSED" if report.policy_passed else "FAILED"

        rows = [
            f"| Total dependencies | {stats.total} |",
            f"| Permissive licenses | {stats.permissive} |",
            f"| Copyleft licenses | {stats.copyleft} |",
            f"| Unknown licenses | {stats.unknown} |",
        ]
        if stats.ignored:
            rows.append(f"| Ignored packages | {stats.ignored} |")
        rows.append(f"| Policy check | {status} |")

        return (
            "\n## Summary\n\n"
            "| Metric | Value |\n"
            "|--------|-------|\n" + "\n".join(rows) + "\n"
        )

    def _dependency_table(self, report: AnalysisReport) -> str:
        lines = [
            "\n## Dependency Licenses\n",
            "| Package | Version | License | Category | Source | Parent |",
            "|---------|---------|---------|----------|--------|--------|",
        ]
        for pkg in sorted(report.packages, key=lambda p: p.name):
            parent = pkg.parent if pkg.parent != pkg.name else "(direct)"
            category = (
                f"{pkg.category.value} (ignored)" if pkg.ignored else pkg.category.value
            )
            lines.append(
                f"| {pkg.name} | {pkg.version} "
                f"| {markdown_license_cell(pkg.display_license)} "
                f"| {category} | {pkg.license_source.value} | {parent} |"
            )
        return "\n".join(lines) + "\n"

    def _ignored_packages(self, report: AnalysisReport) -> str:
        ignored = [p for p in report.packages if p.ignored]
        if not ignored:
            return ""
        lines = [
            "\n## Ignored Packages\n",
            "These packages are exempted from policy evaluation via "
            "`[tool.license-audit.ignored-packages]`.\n",
            "| Package | Version | License | Reason |",
            "|---------|---------|---------|--------|",
        ]
        for pkg in sorted(ignored, key=lambda p: p.name):
            reason = pkg.ignore_reason or "(no reason given)"
            lines.append(
                f"| {pkg.name} | {pkg.version} "
                f"| {markdown_license_cell(pkg.display_license)} | {reason} |"
            )
        return "\n".join(lines) + "\n"

    def _classification_breakdown(self, report: AnalysisReport) -> str:
        counts: dict[str, int] = {}
        for pkg in report.packages:
            cat = pkg.category.value
            counts[cat] = counts.get(cat, 0) + 1

        lines = [
            "\n## License Classification Breakdown\n",
            "| Category | Count |",
            "|----------|-------|",
        ]
        for cat, count in sorted(counts.items()):
            lines.append(f"| {cat} | {count} |")
        return "\n".join(lines) + "\n"

    def _compatibility_analysis(self, report: AnalysisReport) -> str:
        if not report.incompatible_pairs:
            return (
                "\n## Compatibility Analysis\n\nNo incompatible license pairs found.\n"
            )

        lines = [
            "\n## Compatibility Analysis\n",
            "**WARNING: Incompatible license pairs detected!**\n",
            "| License A | License B | Verdict |",
            "|-----------|-----------|---------|",
        ]
        for pair in report.incompatible_pairs:
            lines.append(IncompatiblePairFormatter.markdown_row(pair))
        return "\n".join(lines) + "\n"

    def _recommendations(self, report: AnalysisReport) -> str:
        if not report.recommended_licenses:
            unknown = [
                p
                for p in report.packages
                if not p.ignored and p.category == LicenseCategory.UNKNOWN
            ]
            lines = ["\n## Recommended Licenses\n"]
            if unknown:
                names = ", ".join(f"`{p.name}`" for p in unknown)
                lines.append(
                    f"Cannot recommend a license: {len(unknown)} dependency(ies) "
                    f"have an unrecognized license ({names}). "
                    "Resolve them via `[tool.license-audit.overrides]` and re-run."
                )
            else:
                lines.append("No compatible outbound license found.")
                if report.incompatible_pairs:
                    pairs = ", ".join(
                        f"{p.inbound} / {p.outbound}" for p in report.incompatible_pairs
                    )
                    lines.append(
                        f"The following license pairs have no common outbound "
                        f"license: {pairs}."
                    )
                    lines.append(
                        "Consider adding an override in "
                        "`[tool.license-audit.overrides]` if the detected license "
                        "is incorrect, or replacing the conflicting dependency."
                    )
                else:
                    lines.append(
                        "Your dependencies have license requirements that could not "
                        "be reconciled. Check the Compatibility Analysis section for "
                        "details."
                    )
            return "\n".join(lines) + "\n"

        top = report.recommended_licenses[:10]
        lines = [
            "\n## Recommended Licenses\n",
            "The following licenses are compatible with all your dependencies, "
            "ordered from most to least permissive:\n",
        ]
        for i, lic in enumerate(top, 1):
            cat = self._classifier.classify(lic)
            marker = " **(recommended)**" if i == 1 else ""
            lines.append(f"{i}. **{lic}** ({cat.value}){marker}")

        if len(report.recommended_licenses) > 10:
            lines.append(
                f"\n*...and {len(report.recommended_licenses) - 10} more compatible licenses.*"
            )
        return "\n".join(lines) + "\n"

    def _action_items(self, report: AnalysisReport) -> str:
        if not report.action_items:
            return "\n## Action Items\n\nNo action items.\n"

        lines = ["\n## Action Items\n"]
        for item in report.action_items:
            lines.append(ActionItemFormatter.markdown(item))
        return "\n".join(lines) + "\n"

    def _licenses_requiring_review(self, report: AnalysisReport) -> str:
        """Full license texts for packages whose license couldn't be classified.

        Surfaces the declared identifier (when one exists) alongside the
        bundled license text so the reviewer can read the actual terms and
        decide how to handle the package.
        """
        review = [
            p
            for p in report.packages
            if not p.ignored and p.category == LicenseCategory.UNKNOWN
        ]
        if not review:
            return ""

        lines = [
            "\n## Licenses Requiring Review\n",
            "These packages have a license that could not be mapped to a known "
            "SPDX identifier. The full license text is included below so you can "
            "review the terms and, if appropriate, record the correct license "
            "via `[tool.license-audit.overrides]`.\n",
        ]
        for pkg in sorted(review, key=lambda p: p.name):
            lines.append(f"\n### {pkg.name} {pkg.version}\n")
            if pkg.declared_license:
                lines.append(
                    f"- **Declared license:** {license_label(pkg.declared_license)}"
                )
            else:
                lines.append("- **License:** not detected")
            lines.append(f"- **Source:** {pkg.license_source.value}")
            # Prefer a bundled LICENSE file; fall back to the declared string
            # itself, since some packages put the full text in the metadata.
            text = pkg.license_text or pkg.declared_license
            if text:
                lines.append(f"\n{fenced_code_block(text)}\n")
            else:
                lines.append(
                    "\n*License text not available. Refer to the package "
                    "distribution for the full license.*\n"
                )
        return "\n".join(lines) + "\n"

    def _footer(self) -> str:
        return attribution_footer(
            "This report is for informational purposes only and does not constitute legal advice.",
        )
