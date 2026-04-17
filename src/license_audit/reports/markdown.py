"""Markdown compliance report renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import UNKNOWN_LICENSE, AnalysisReport, LicenseCategory


class MarkdownRenderer:
    """Render analysis report as a Markdown compliance document."""

    def __init__(self, classifier: LicenseClassifier | None = None) -> None:
        self._classifier = classifier or LicenseClassifier()

    def render(self, report: AnalysisReport) -> str:
        """Render the report as Markdown."""
        sections = [
            self._header(report),
            self._summary(report),
            self._dependency_table(report),
            self._classification_breakdown(report),
            self._compatibility_analysis(report),
            self._recommendations(report),
            self._action_items(report),
            self._footer(),
        ]
        return "\n".join(sections)

    def _header(self, report: AnalysisReport) -> str:
        now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"# License Compliance Report: {report.project_name}\n\nGenerated: {now}\n"
        )

    def _summary(self, report: AnalysisReport) -> str:
        total = len(report.packages)
        unknown = sum(
            1 for p in report.packages if p.license_expression == UNKNOWN_LICENSE
        )
        copyleft = sum(
            1
            for p in report.packages
            if p.category
            in (
                LicenseCategory.STRONG_COPYLEFT,
                LicenseCategory.WEAK_COPYLEFT,
                LicenseCategory.NETWORK_COPYLEFT,
            )
        )
        permissive = sum(
            1 for p in report.packages if p.category == LicenseCategory.PERMISSIVE
        )

        status = "PASSED" if report.policy_passed else "FAILED"

        return (
            f"\n## Summary\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Total dependencies | {total} |\n"
            f"| Permissive licenses | {permissive} |\n"
            f"| Copyleft licenses | {copyleft} |\n"
            f"| Unknown licenses | {unknown} |\n"
            f"| Policy check | {status} |\n"
        )

    def _dependency_table(self, report: AnalysisReport) -> str:
        lines = [
            "\n## Dependency Licenses\n",
            "| Package | Version | License | Category | Source | Parent |",
            "|---------|---------|---------|----------|--------|--------|",
        ]
        for pkg in sorted(report.packages, key=lambda p: p.name):
            parent = pkg.parent if pkg.parent != pkg.name else "(direct)"
            lines.append(
                f"| {pkg.name} | {pkg.version} | {pkg.license_expression} "
                f"| {pkg.category.value} | {pkg.license_source.value} | {parent} |"
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
            lines.append(f"| {pair.inbound} | {pair.outbound} | {pair.verdict.value} |")
        return "\n".join(lines) + "\n"

    def _recommendations(self, report: AnalysisReport) -> str:
        if not report.recommended_licenses:
            lines = [
                "\n## Recommended Licenses\n",
                "No compatible outbound license found.",
            ]
            if report.incompatible_pairs:
                pairs = ", ".join(
                    f"{p.inbound} / {p.outbound}" for p in report.incompatible_pairs
                )
                lines.append(
                    f"The following license pairs have no common outbound license: {pairs}."
                )
                lines.append(
                    "Consider adding an override in `[tool.license-audit.overrides]` if the "
                    "detected license is incorrect, or replacing the conflicting dependency."
                )
            else:
                lines.append(
                    "Your dependencies have license requirements that could not be "
                    "reconciled. Check the Compatibility Analysis section for details."
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
            icon = "Warning" if item.severity == "warning" else "Error"
            pkg_prefix = f"**{item.package}**: " if item.package else ""
            lines.append(f"- [{icon}] {pkg_prefix}{item.message}")
        return "\n".join(lines) + "\n"

    def _footer(self) -> str:
        return (
            "\n---\n\n"
            "*Generated by [license_audit](https://github.com/dgeragh/license-audit). "
            "This report is for informational purposes only and does not constitute legal advice.*\n"
        )
