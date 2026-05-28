"""Rich terminal output for analysis reports."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from license_audit.core.models import AnalysisReport, LicenseCategory
from license_audit.reports._format import (
    ActionItemFormatter,
    IncompatiblePairFormatter,
    SummaryStats,
    category_label,
    deemed_constraint_packages,
    license_label,
)


class TerminalRenderer:
    """Renders an analysis report to a Rich console."""

    CATEGORY_COLORS: dict[LicenseCategory, str] = {
        LicenseCategory.PERMISSIVE: "green",
        LicenseCategory.WEAK_COPYLEFT: "yellow",
        LicenseCategory.STRONG_COPYLEFT: "orange1",
        LicenseCategory.NETWORK_COPYLEFT: "red",
        LicenseCategory.PROPRIETARY: "magenta",
        LicenseCategory.UNKNOWN: "bright_red",
    }

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def render(self, report: AnalysisReport) -> None:
        """Write `report` to the attached console."""
        self._render_header(report)
        self._render_package_table(report)
        self._render_ignored(report)
        self._render_compatibility(report)
        self._render_recommendations(report)
        self._render_action_items(report)
        self._render_summary(report)

    def _render_header(self, report: AnalysisReport) -> None:
        self._console.print()
        self._console.rule(f"[bold]License Analysis: {report.project_name}[/bold]")
        if report.source:
            self._console.print(f"[dim]Source:[/dim] {report.source}")
        self._console.print()

    def _render_package_table(self, report: AnalysisReport) -> None:
        table = Table(title="Dependency Licenses", show_lines=False)
        table.add_column("Package", style="cyan")
        table.add_column("Version", style="dim")
        table.add_column("License", style="bold")
        table.add_column("Category")
        table.add_column("Source", style="dim")
        table.add_column("Parent", style="dim")

        for pkg in sorted(report.packages, key=lambda p: p.name):
            color = self.CATEGORY_COLORS.get(pkg.category, "white")
            category_text = Text(
                category_label(pkg), style="dim" if pkg.ignored else color
            )
            parent = pkg.parent if pkg.parent != pkg.name else "(direct)"
            row_style = "dim" if pkg.ignored else ""
            table.add_row(
                pkg.name,
                pkg.version,
                Text(license_label(pkg.display_license)),
                category_text,
                pkg.license_source.value,
                parent,
                style=row_style,
            )

        self._console.print(table)
        self._console.print()

    def _render_ignored(self, report: AnalysisReport) -> None:
        ignored = [p for p in report.packages if p.ignored]
        if not ignored:
            return
        self._console.print("[bold]Ignored Packages:[/bold]")
        for pkg in sorted(ignored, key=lambda p: p.name):
            reason = pkg.ignore_reason or "(no reason given)"
            self._console.print(f"  [dim]- {pkg.name}[/dim]: {escape(reason)}")
        self._console.print()

    def _render_compatibility(self, report: AnalysisReport) -> None:
        if not report.incompatible_pairs:
            return

        self._console.print("[bold red]Incompatible License Pairs:[/bold red]")
        for pair in report.incompatible_pairs:
            self._console.print(IncompatiblePairFormatter.rich(pair))
        self._console.print()

    def _render_recommendations(self, report: AnalysisReport) -> None:
        if not report.recommended_licenses:
            unknown = [
                p
                for p in report.packages
                if not p.ignored and p.category == LicenseCategory.UNKNOWN
            ]
            deemed = deemed_constraint_packages(report)
            if unknown:
                names = ", ".join(p.name for p in unknown)
                self._console.print(
                    "[bold yellow]Cannot recommend a license[/bold yellow] until "
                    f"{len(unknown)} unrecognized license(s) are resolved: {names}",
                )
            elif deemed:
                names = ", ".join(p.name for p in deemed)
                self._console.print(
                    "[bold yellow]Cannot recommend a license[/bold yellow]: "
                    f"{len(deemed)} dependency(ies) are classified as a "
                    "non-permissive license with no SPDX id, so outbound "
                    f"compatibility can't be computed: {names}. Map them to an "
                    "SPDX id via [tool.license-audit.overrides] for recommendations.",
                )
            else:
                self._console.print(
                    "[bold red]No compatible outbound license found![/bold red]",
                )
                if report.incompatible_pairs:
                    for pair in report.incompatible_pairs:
                        self._console.print(
                            f"  [red]\\[x][/red] {pair.inbound} and {pair.outbound} "
                            "have no common outbound license",
                        )
            self._console.print()
            return

        self._console.print(
            "[bold]Recommended Outbound Licenses[/bold] (most -> least permissive):",
        )
        for i, lic in enumerate(report.recommended_licenses[:10]):
            marker = "->" if i == 0 else "  "
            if i == 0:
                self._console.print(f"  {marker} [bold green]{lic}[/bold green]")
            else:
                self._console.print(f"  {marker} {lic}")
        if len(report.recommended_licenses) > 10:
            self._console.print(
                f"  ... and {len(report.recommended_licenses) - 10} more",
            )
        self._console.print()

    def _render_action_items(self, report: AnalysisReport) -> None:
        if not report.action_items:
            return

        self._console.print("[bold]Action Items:[/bold]")
        for item in report.action_items:
            self._console.print(ActionItemFormatter.rich(item))
        self._console.print()

    def _render_summary(self, report: AnalysisReport) -> None:
        stats = SummaryStats.from_report(report)

        self._console.rule("[bold]Summary[/bold]")
        self._console.print(f"  Total dependencies: {stats.total}")
        self._console.print(f"  Unknown licenses:   {stats.unknown}")
        self._console.print(f"  Copyleft licenses:  {stats.copyleft}")
        if stats.ignored:
            self._console.print(f"  Ignored packages:   {stats.ignored}")

        if report.policy_passed is not None:
            if report.policy_passed:
                self._console.print(
                    "  Policy check:       [bold green]PASSED[/bold green]",
                )
            else:
                self._console.print(
                    "  Policy check:       [bold red]FAILED[/bold red]",
                )

        self._console.print()
