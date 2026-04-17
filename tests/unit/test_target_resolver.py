"""Tests for TargetResolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.core.analyzer import TargetResolver


class TestTargetResolver:
    def test_none_target_uses_cwd(self) -> None:
        info = TargetResolver().resolve(None)
        assert info.config_dir == Path.cwd()
        assert info.source_path is None
        assert info.site_packages is None

    def test_file_target_uv_lock(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text(
            "version = 1\n[[package]]\nname = 'root'\nversion = '0.1'\n",
        )
        info = TargetResolver().resolve(lock_file)
        assert info.source_path == lock_file.resolve()
        assert info.config_dir == lock_file.resolve().parent

    def test_file_target_requirements(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("click>=8.0\n")
        info = TargetResolver().resolve(req_file)
        assert info.source_path is not None

    def test_file_target_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["click"]\n')
        info = TargetResolver().resolve(pyproject)
        assert info.source_path is not None

    def test_unrecognized_file_raises(self, tmp_path: Path) -> None:
        unknown = tmp_path / "deps.yaml"
        unknown.write_text("")
        with pytest.raises(ValueError, match="Unrecognized dependency file"):
            TargetResolver().resolve(unknown)

    def test_project_dir_detects_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["click"]\n',
        )
        info = TargetResolver().resolve(tmp_path)
        assert info.source_path is not None
        assert info.source_path.name == "pyproject.toml"

    def test_project_dir_prefers_uv_lock(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["click"]\n',
        )
        (tmp_path / "requirements.txt").write_text("click\n")
        (tmp_path / "uv.lock").write_text("version = 1\n")
        info = TargetResolver().resolve(tmp_path)
        assert info.source_path is not None
        assert info.source_path.name == "uv.lock"

    def test_empty_project_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            TargetResolver().resolve(tmp_path)

    def test_nonexistent_target_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            TargetResolver().resolve(tmp_path / "nonexistent")
