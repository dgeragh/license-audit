"""The `check` CLI command, license policy validation."""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.markup import escape

from license_audit.cli._common import resolve_config
from license_audit.config import LicenseAuditConfig
from license_audit.core.analyzer import LicenseAuditor
from license_audit.core.models import (
    UNKNOWN_LICENSE,
    AnalysisReport,
    LicenseCategory,
    PackageLicense,
)


def _determine_exit_code(
    report: AnalysisReport,
    unknown_pkgs: list[PackageLicense],
    config: LicenseAuditConfig,
) -> int:
    if report.incompatible_pairs:
        return 1
    if report.policy_passed is False:
        return 1
    if unknown_pkgs and config.fail_on_unknown:
        return 2
    return 0


def _print_result(
    console: Console,
    report: AnalysisReport,
    unknown_pkgs: list[PackageLicense],
    exit_code: int,
) -> None:
    if exit_code == 1 and report.incompatible_pairs:
        console.print("[bold red]FAIL:[/bold red] Incompatible license pairs found.")
        for pair in report.incompatible_pairs:
            console.print(f"  [red]\\[x][/red] {pair.inbound} <-> {pair.outbound}")
    elif exit_code == 1:
        console.print("[bold red]FAIL:[/bold red] License policy check failed.")
        for item in report.action_items:
            if item.severity == "error":
                console.print(f"  [red]\\[x][/red] {escape(item.message)}")
    elif exit_code == 2:
        names = [p.name for p in unknown_pkgs]
        console.print(
            f"[bold yellow]UNKNOWN:[/bold yellow] {len(names)} package(s) "
            f"with undetected licenses: {', '.join(names)}"
        )

    # Always print warnings (actionable guidance regardless of pass/fail)
    warnings = [i for i in report.action_items if i.severity == "warning"]
    if warnings:
        console.print()
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for item in warnings:
            console.print(f"  [yellow]\\[!][/yellow] {escape(item.message)}")

    if exit_code == 0:
        console.print(
            f"[bold green]OK:[/bold green] {len(report.packages)} dependencies checked, "
            f"all clear."
        )


@click.command("check")
@click.option(
    "--fail-on-unknown/--no-fail-on-unknown",
    default=None,
    help="Fail if any dependency has an unknown license.",
)
@click.pass_context
def check_cmd(ctx: click.Context, fail_on_unknown: bool | None) -> None:
    """License policy check.

    Exit codes:
      0 = all clear
      1 = policy violation
      2 = unknown licenses found (when --fail-on-unknown)
    """
    console = Console(stderr=True)
    target, config = resolve_config(ctx)
    if fail_on_unknown is not None:
        config.fail_on_unknown = fail_on_unknown

    report = LicenseAuditor().run(target=target, config=config)

    unknown_pkgs = [
        p
        for p in report.packages
        if p.license_expression == UNKNOWN_LICENSE
        or p.category == LicenseCategory.UNKNOWN
    ]

    exit_code = _determine_exit_code(report, unknown_pkgs, config)
    _print_result(console, report, unknown_pkgs, exit_code)
    sys.exit(exit_code)
