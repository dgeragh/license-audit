"""The `analyze` CLI command."""

from __future__ import annotations

import click

from license_audit.cli._common import resolve_config, run_audit
from license_audit.reports.json_report import JsonRenderer
from license_audit.reports.terminal import TerminalRenderer


@click.command("analyze")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    help="Output format.",
)
@click.pass_context
def analyze_cmd(ctx: click.Context, output_format: str) -> None:
    """Scan dependencies and show license analysis."""
    target, config = resolve_config(ctx)

    report = run_audit(target, config)

    if output_format == "json":
        click.echo(JsonRenderer().render(report))
    else:
        TerminalRenderer().render(report)
