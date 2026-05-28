"""Tests for TargetResolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.core.analyzer import TargetResolver


def _make_venv(path: Path) -> Path:
    (path / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    return path


class TestTargetResolver:
    def test_none_target_without_venv_uses_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        info = TargetResolver().resolve(None)
        assert info.config_dir == tmp_path
        assert info.site_packages is None

    def test_none_target_prefers_cwd_venv(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _make_venv(tmp_path / ".venv")
        monkeypatch.chdir(tmp_path)
        info = TargetResolver().resolve(None)
        assert info.site_packages == tmp_path / ".venv"
        assert info.config_dir == tmp_path

    def test_file_target_raises(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text("version = 1\n")
        with pytest.raises(ValueError, match="is a file"):
            TargetResolver().resolve(lock_file)

    def test_venv_dir_target(self, tmp_path: Path) -> None:
        venv = _make_venv(tmp_path / ".venv")
        info = TargetResolver().resolve(venv)
        assert info.site_packages == venv.resolve()
        assert info.config_dir == venv.resolve().parent

    def test_project_dir_with_venv(self, tmp_path: Path) -> None:
        _make_venv(tmp_path / ".venv")
        info = TargetResolver().resolve(tmp_path)
        assert info.site_packages == (tmp_path / ".venv").resolve()
        assert info.config_dir == tmp_path.resolve()

    def test_project_dir_without_venv_raises(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        with pytest.raises(FileNotFoundError, match="No virtualenv found"):
            TargetResolver().resolve(tmp_path)

    def test_nonexistent_target_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            TargetResolver().resolve(tmp_path / "nonexistent")
