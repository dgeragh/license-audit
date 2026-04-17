"""The `report` CLI command, generate compliance documents."""

from __future__ import annotations

from pathlib import Path

import click

from license_audit.cli._common import resolve_config
from license_audit.core.analyzer import LicenseAuditor
from license_audit.reports.base import ReportRenderer
from license_audit.reports.json_report import JsonRenderer
from license_audit.reports.markdown import MarkdownRenderer
from license_audit.reports.notices import NoticesRenderer


@click.command("report")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json", "notices"]),
    default="markdown",
    help="Report format.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (defaults to stdout).",
)
@click.pass_context
def report_cmd(
    ctx: click.Context, output_format: str, output_path: Path | None
) -> None:
    """Generate a license compliance report."""
    target, config = resolve_config(ctx)

    report = LicenseAuditor().run(target=target, config=config)

    renderer: ReportRenderer
    if output_format == "json":
        renderer = JsonRenderer()
    elif output_format == "notices":
        renderer = NoticesRenderer()
    else:
        renderer = MarkdownRenderer()

    content = renderer.render(report)

    if output_path:
        output_path.write_text(content)
        click.echo(f"Report written to {output_path}")
    else:
        click.echo(content)
