"""CLI entry point for license_audit."""

from __future__ import annotations

from pathlib import Path

import click

from license_audit.cli.analyze import analyze_cmd
from license_audit.cli.check import check_cmd
from license_audit.cli.recommend import recommend_cmd
from license_audit.cli.refresh import refresh_cmd
from license_audit.cli.report import report_cmd
from license_audit.core.models import PolicyLevel


@click.group()
@click.option(
    "--target",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Project directory or virtualenv to analyze.",
)
@click.option(
    "--policy",
    type=click.Choice([p.value for p in PolicyLevel]),
    default=None,
    help="License policy level. Overrides [tool.license-audit] config.",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "pyproject.toml (or its directory) to read config and project name "
        "from. Defaults to the target's location."
    ),
)
@click.version_option(package_name="license-audit")
@click.pass_context
def cli(
    ctx: click.Context,
    target: Path | None,
    policy: str | None,
    config: Path | None,
) -> None:
    """license-audit: Analyze dependency licenses for Python projects."""
    ctx.ensure_object(dict)
    ctx.obj["target"] = target
    ctx.obj["policy"] = policy
    ctx.obj["config"] = config


cli.add_command(analyze_cmd, "analyze")
cli.add_command(check_cmd, "check")
cli.add_command(recommend_cmd, "recommend")
cli.add_command(report_cmd, "report")
cli.add_command(refresh_cmd, "refresh")
