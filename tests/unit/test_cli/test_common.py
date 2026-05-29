"""Tests for cli._common.resolve_config."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from license_audit.cli._common import resolve_config
from license_audit.core.models import PolicyLevel


def _ctx(
    target: Path | None = None,
    policy: str | None = None,
    config: Path | None = None,
) -> SimpleNamespace:
    """A minimal click.Context stand-in exposing just ``obj``."""
    return SimpleNamespace(
        obj={
            "target": target,
            "policy": policy,
            "config": config,
        },
    )


def _make_venv(path: Path) -> Path:
    (path / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    return path


class TestResolveConfig:
    def test_no_target_uses_cwd_defaults(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        target, config, config_dir = resolve_config(_ctx())  # type: ignore[arg-type]
        assert target is None
        assert config.policy == PolicyLevel.PERMISSIVE
        assert config_dir == tmp_path

    def test_directory_target_loads_config_from_it(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.license-audit]\npolicy = "weak-copyleft"\n',
        )
        target, config, config_dir = resolve_config(_ctx(target=tmp_path))  # type: ignore[arg-type]
        assert target == tmp_path
        assert config_dir == tmp_path
        assert config.policy == PolicyLevel.WEAK_COPYLEFT

    def test_venv_target_reads_config_from_parent(self, tmp_path: Path) -> None:
        """A venv target loads config from the directory beside it."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.license-audit]\npolicy = "weak-copyleft"\n',
        )
        venv = _make_venv(tmp_path / ".venv")
        _target, config, config_dir = resolve_config(_ctx(target=venv))  # type: ignore[arg-type]
        assert config_dir == tmp_path
        assert config.policy == PolicyLevel.WEAK_COPYLEFT

    def test_policy_flag_overrides_config(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.license-audit]\npolicy = "permissive"\n',
        )
        _target, config, _dir = resolve_config(
            _ctx(target=tmp_path, policy="network-copyleft"),  # type: ignore[arg-type]
        )
        assert config.policy == PolicyLevel.NETWORK_COPYLEFT

    def test_config_override_directory(self, tmp_path: Path) -> None:
        """--config points config resolution at a separate directory."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "pyproject.toml").write_text(
            '[tool.license-audit]\npolicy = "strong-copyleft"\n',
        )
        venv = _make_venv(tmp_path / "env")
        _target, config, config_dir = resolve_config(
            _ctx(target=venv, config=proj),  # type: ignore[arg-type]
        )
        assert config_dir == proj
        assert config.policy == PolicyLevel.STRONG_COPYLEFT

    def test_config_override_file_uses_parent(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        pyproject = proj / "pyproject.toml"
        pyproject.write_text('[tool.license-audit]\npolicy = "network-copyleft"\n')
        _target, config, config_dir = resolve_config(_ctx(config=pyproject))  # type: ignore[arg-type]
        assert config_dir == proj
        assert config.policy == PolicyLevel.NETWORK_COPYLEFT

    def test_config_target_used_when_cli_target_absent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`target` in `[tool.license-audit]` is used when --target is omitted."""
        project = tmp_path / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text(
            '[tool.license-audit]\ntarget = "."\n',
        )
        # CWD is the project so load_config(None) finds this pyproject.
        monkeypatch.chdir(project)
        target, config, _dir = resolve_config(_ctx())  # type: ignore[arg-type]
        assert config.target == "."
        assert target == project.resolve()

    def test_config_target_resolved_against_pyproject_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Relative `target` resolves against the pyproject's directory."""
        project = tmp_path / "proj"
        project.mkdir()
        sibling = tmp_path / "sibling"
        sibling.mkdir()
        (project / "pyproject.toml").write_text(
            '[tool.license-audit]\ntarget = "../sibling"\n',
        )
        # CWD is the project; CLI target absent so config.target kicks in.
        monkeypatch.chdir(project)
        target, _config, _dir = resolve_config(_ctx())  # type: ignore[arg-type]
        assert target == sibling.resolve()

    def test_cli_target_overrides_config_target(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text(
            '[tool.license-audit]\ntarget = "/should/be/ignored"\n',
        )
        target, _config, _dir = resolve_config(_ctx(target=project))  # type: ignore[arg-type]
        assert target == project
