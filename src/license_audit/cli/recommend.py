"""The `recommend` CLI command."""

from __future__ import annotations

import click
from rich.console import Console
from rich.panel import Panel

from license_audit.cli._common import resolve_config, run_audit
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import (
    CATEGORY_RANK,
    AnalysisReport,
    LicenseCategory,
    PackageLicense,
)
from license_audit.reports._format import (
    ActionItemFormatter,
    IncompatiblePairFormatter,
)

_classifier = LicenseClassifier()


class CategoryDescriptions:
    """Human-readable copy and guidance for each license category."""

    DESCRIPTIONS: dict[LicenseCategory, str] = {
        LicenseCategory.PERMISSIVE: (
            "No copyleft obligations. You can use any license, including proprietary."
        ),
        LicenseCategory.WEAK_COPYLEFT: (
            "Modifications to the dependency itself must be shared, "
            "but your code can use a different license."
        ),
        LicenseCategory.STRONG_COPYLEFT: (
            "Your entire project must use a compatible copyleft license."
        ),
        LicenseCategory.NETWORK_COPYLEFT: (
            "Like strong copyleft, but also applies to network use (SaaS). "
            "Your project must use a compatible license."
        ),
        LicenseCategory.PROPRIETARY: "Proprietary dependencies may restrict distribution.",
        LicenseCategory.UNKNOWN: "License could not be determined. Manual review required.",
    }

    GUIDANCE: dict[LicenseCategory, list[str]] = {
        LicenseCategory.PERMISSIVE: [
            "All your dependencies use permissive licenses. "
            "You are free to choose any license, including proprietary.",
            "",
            "Common choices: MIT (simplest), Apache-2.0 (patent grant), "
            "BSD-3-Clause (attribution).",
        ],
        LicenseCategory.WEAK_COPYLEFT: [
            "You have weak-copyleft dependencies (e.g., LGPL, MPL). "
            "Pick from the 'Compatible licenses' list above: the OSADL matrix "
            "takes a strict view of weak-copyleft compatibility, so permissive "
            "outbound licenses are typically excluded.",
            "",
            "In practice, dynamic linking or shipping the dependency unmodified "
            "may allow a broader set of outbound licenses than the matrix suggests. "
            "Verify any exceptions with legal review.",
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

    @classmethod
    def describe(cls, category: LicenseCategory) -> str:
        return cls.DESCRIPTIONS.get(category, "")

    @classmethod
    def guidance(cls, category: LicenseCategory) -> list[str]:
        return cls.GUIDANCE.get(category, [])


@click.command("recommend")
@click.pass_context
def recommend_cmd(ctx: click.Context) -> None:
    """Recommend a license for your project based on dependencies."""
    console = Console()
    target, config = resolve_config(ctx)

    report = run_audit(target, config)

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
    """Return the package with the most restrictive license category."""
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
    """Print the most restrictive dependency and what it means."""
    if pkg and category != LicenseCategory.PERMISSIVE:
        console.print(
            f"[bold yellow]Most restrictive dependency:[/bold yellow] "
            f"{pkg.name} ({pkg.license_expression})"
        )
        desc = CategoryDescriptions.describe(category)
        if desc:
            console.print(f"  {desc}")
        console.print()


def _render_recommendations(console: Console, report: AnalysisReport) -> None:
    """Print the recommended licenses and guidance panel."""
    if not report.recommended_licenses:
        console.print(
            "[bold red]No compatible outbound license found![/bold red]\n"
            "Your dependencies have conflicting license requirements."
        )
        if report.incompatible_pairs:
            console.print("\n[bold]Conflicting pairs:[/bold]")
            for pair in report.incompatible_pairs:
                console.print(IncompatiblePairFormatter.rich(pair))
        return

    top = report.recommended_licenses[:5]
    console.print("[bold]Compatible licenses for your project:[/bold]")
    for i, lic in enumerate(top):
        cat = _classifier.classify(lic)
        if i == 0:
            console.print(
                f"  [bold green]-> {lic}[/bold green] ({cat.value}) "
                f"[dim]<- recommended[/dim]"
            )
        else:
            console.print(f"    {lic} ({cat.value})")
    console.print()

    most_cat, _ = _find_most_restrictive(report.packages)
    guidance = CategoryDescriptions.guidance(most_cat)
    if guidance:
        console.print(Panel("\n".join(guidance), title="Guidance", border_style="blue"))


def _render_action_items(console: Console, report: AnalysisReport) -> None:
    """Print any action items from the report."""
    if not report.action_items:
        return
    console.print()
    console.print("[bold]Action items:[/bold]")
    for item in report.action_items:
        console.print(ActionItemFormatter.rich(item))
