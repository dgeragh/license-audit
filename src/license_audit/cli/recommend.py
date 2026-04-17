"""The `recommend` CLI command."""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from license_audit.cli._common import resolve_config
from license_audit.core.analyzer import LicenseAuditor
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import (
    CATEGORY_RANK,
    AnalysisReport,
    LicenseCategory,
    PackageLicense,
)

_classifier = LicenseClassifier()

_CATEGORY_DESCRIPTIONS: dict[LicenseCategory, str] = {
    LicenseCategory.PERMISSIVE: "No copyleft obligations. You can use any license, including proprietary.",
    LicenseCategory.WEAK_COPYLEFT: "Modifications to the dependency itself must be shared, but your code can use a different license.",
    LicenseCategory.STRONG_COPYLEFT: "Your entire project must use a compatible copyleft license.",
    LicenseCategory.NETWORK_COPYLEFT: "Like strong copyleft, but also applies to network use (SaaS). Your project must use a compatible license.",
    LicenseCategory.PROPRIETARY: "Proprietary dependencies may restrict distribution.",
    LicenseCategory.UNKNOWN: "License could not be determined. Manual review required.",
}


@click.command("recommend")
@click.pass_context
def recommend_cmd(ctx: click.Context) -> None:
    """Recommend a license for your project based on dependencies."""
    console = Console()
    target, config = resolve_config(ctx)

    report = LicenseAuditor().run(target=target, config=config)

    console.print()
    console.rule(f"[bold]License Recommendation: {report.project_name}[/bold]")
    console.print()

    if not report.packages:
        console.print("No dependencies found. You can use any license.")
        return

    most_restrictive_cat, most_restrictive_pkg = _find_most_restrictive(report.packages)
    _render_constraint(console, most_restrictive_cat, most_restrictive_pkg)
    _render_recommendations(console, report)
    _render_action_items(console, report)
    console.print()


def _find_most_restrictive(
    packages: list[PackageLicense],
) -> tuple[LicenseCategory, PackageLicense | None]:
    """Find the most restrictive dependency by license category."""
    most_cat = LicenseCategory.PERMISSIVE
    most_pkg: PackageLicense | None = None
    for pkg in packages:
        if CATEGORY_RANK.get(pkg.category, 0) > CATEGORY_RANK.get(most_cat, 0):
            most_cat = pkg.category
            most_pkg = pkg
    return most_cat, most_pkg


def _render_constraint(
    console: Console,
    category: LicenseCategory,
    pkg: PackageLicense | None,
) -> None:
    """Render the most restrictive dependency constraint."""
    if pkg and category != LicenseCategory.PERMISSIVE:
        console.print(
            f"[bold yellow]Most restrictive dependency:[/bold yellow] "
            f"{pkg.name} ({pkg.license_expression})"
        )
        desc = _CATEGORY_DESCRIPTIONS.get(category, "")
        if desc:
            console.print(f"  {desc}")
        console.print()


def _render_recommendations(console: Console, report: AnalysisReport) -> None:
    """Render license recommendations and guidance."""
    if not report.recommended_licenses:
        console.print(
            "[bold red]No compatible outbound license found![/bold red]\n"
            "Your dependencies have conflicting license requirements."
        )
        if report.incompatible_pairs:
            console.print("\n[bold]Conflicting pairs:[/bold]")
            for pair in report.incompatible_pairs:
                console.print(f"  \\[x] {pair.inbound} <-> {pair.outbound}")
        return

    top = report.recommended_licenses[:5]
    console.print("[bold]Compatible licenses for your project:[/bold]")
    for i, lic in enumerate(top):
        cat = _classifier.classify(lic)
        if i == 0:
            console.print(
                f"  [bold green]-> {lic}[/bold green] ({cat.value}) [dim]<- recommended[/dim]"
            )
        else:
            console.print(f"    {lic} ({cat.value})")
    console.print()

    most_cat, _ = _find_most_restrictive(report.packages)
    guidance = _build_guidance(most_cat)
    if guidance:
        console.print(Panel("\n".join(guidance), title="Guidance", border_style="blue"))


def _render_action_items(console: Console, report: AnalysisReport) -> None:
    """Render action items."""
    if not report.action_items:
        return
    console.print()
    console.print("[bold]Action items:[/bold]")
    for item in report.action_items:
        icon = "\\[!]" if item.severity == "warning" else "\\[x]"
        color = "yellow" if item.severity == "warning" else "red"
        console.print(f"  [{color}]{icon}[/{color}] {escape(item.message)}")


def _build_guidance(most_restrictive: LicenseCategory) -> list[str]:
    """Build guidance text based on the most restrictive license category."""
    guidance_map: dict[LicenseCategory, list[str]] = {
        LicenseCategory.PERMISSIVE: [
            "All your dependencies use permissive licenses. "
            "You are free to choose any license, including proprietary.",
            "",
            "Common choices: MIT (simplest), Apache-2.0 (patent grant), "
            "BSD-3-Clause (attribution).",
        ],
        LicenseCategory.WEAK_COPYLEFT: [
            "You have weak-copyleft dependencies (e.g., LGPL, MPL). "
            "Your project can use a different license, but modifications "
            "to those specific dependencies must be shared under their original license.",
            "",
            "If you distribute as a library: ensure the weak-copyleft "
            "components can be replaced by users (dynamic linking).",
        ],
        LicenseCategory.STRONG_COPYLEFT: [
            "You have strong-copyleft dependencies (e.g., GPL). "
            "Your entire project must be licensed under a GPL-compatible license.",
            "",
            "If this is not acceptable, you must find alternative "
            "dependencies with permissive licenses.",
        ],
        LicenseCategory.NETWORK_COPYLEFT: [
            "You have network-copyleft dependencies (e.g., AGPL). "
            "Your project must be licensed under AGPL or compatible, "
            "even for network/SaaS use.",
            "",
            "This is the most restrictive category. Users who interact "
            "with your software over a network must be able to receive the source.",
        ],
        LicenseCategory.UNKNOWN: [
            "Some dependencies have unknown licenses. You must determine "
            "their licenses manually before distributing your project.",
            "",
            "Use [tool.license-audit.overrides] in pyproject.toml to set "
            "licenses for packages where detection fails.",
        ],
    }
    return guidance_map.get(most_restrictive, [])
