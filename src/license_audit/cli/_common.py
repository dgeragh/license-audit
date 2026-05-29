"""Shared CLI helpers."""

from __future__ import annotations

from pathlib import Path

import click

from license_audit.config import LicenseAuditConfig, load_config
from license_audit.core.analyzer import LicenseAuditor
from license_audit.core.models import AnalysisReport, PolicyLevel
from license_audit.environment.venv import is_venv_dir


def resolve_config(
    ctx: click.Context,
) -> tuple[Path | None, LicenseAuditConfig, Path | None]:
    """Extract the target, merged config, and config directory from the CLI.

    CLI flags (--target, --policy, --config) override values read from
    pyproject.toml. --config decides where config and the project name
    are read from; otherwise that follows the target.
    """
    target: Path | None = ctx.obj.get("target")
    policy: str | None = ctx.obj.get("policy")
    config_override: Path | None = ctx.obj.get("config")

    config_dir = _config_dir(target, config_override)
    config = load_config(config_dir)
    if policy is not None:
        config.policy = PolicyLevel(policy)
    if target is None and config.target is not None:
        # Resolve relative paths against the config dir so config is
        # portable across CI/dev machines regardless of CWD.
        base = config_dir if config_dir is not None else Path.cwd()
        target = (base / config.target).resolve()
    return target, config, config_dir


def _config_dir(target: Path | None, config_override: Path | None) -> Path | None:
    """Directory to read [tool.license-audit] and the project name from."""
    if config_override is not None:
        return config_override.parent if config_override.is_file() else config_override
    if target is None:
        return Path.cwd()
    if target.is_file() or is_venv_dir(target):
        return target.parent
    return target


def run_audit(
    target: Path | None,
    config: LicenseAuditConfig,
    config_dir: Path | None = None,
    auditor: LicenseAuditor | None = None,
) -> AnalysisReport:
    """Run the audit and convert user-facing errors to clean CLI messages.

    Raises `click.ClickException` on target-resolution errors so Click
    prints a concise "Error: ..." instead of a full Python traceback.
    """
    try:
        return (auditor or LicenseAuditor()).run(
            target=target,
            config=config,
            config_dir=config_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
