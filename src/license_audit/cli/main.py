"""CLI entry point for license_audit."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from license_audit.cli.analyze import analyze_cmd
from license_audit.cli.check import check_cmd
from license_audit.cli.recommend import recommend_cmd
from license_audit.cli.refresh import refresh_cmd
from license_audit.cli.report import report_cmd
from license_audit.core.models import PolicyLevel


class _Group(click.Group):
    """Exit 1 on every error.

    Click exits 2 on a usage error, which `check` reserves for "unknown
    licenses only"; a bad flag or path would otherwise pass as a warning in
    CI.
    """

    def main(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["standalone_mode"] = False
        try:
            return super().main(*args, **kwargs)
        except click.ClickException as exc:
            exc.show()
            sys.exit(1)
        except click.Abort:
            click.echo("Aborted!", err=True)
            sys.exit(1)


@click.group(cls=_Group)
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
