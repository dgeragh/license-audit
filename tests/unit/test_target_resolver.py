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
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
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


class TestDefaultTarget:
    """With no target: the project's .venv, then $VIRTUAL_ENV, then ours."""

    @pytest.fixture(autouse=True)
    def _no_active_venv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    def test_finds_project_from_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        venv = _make_venv(tmp_path / ".venv")
        sub = tmp_path / "src" / "x"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        info = TargetResolver().resolve(None)
        assert info.site_packages == venv
        assert info.config_dir == tmp_path

    def test_project_search_stops_at_repository_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "outside"\n')
        _make_venv(tmp_path / ".venv")
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        sub = repo / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        info = TargetResolver().resolve(None)
        assert info.site_packages is None
        assert info.config_dir == sub

    def test_activated_virtualenv_used_when_project_has_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text('[project]\nname = "x"\n')
        active = _make_venv(tmp_path / "envs" / "x")
        monkeypatch.setenv("VIRTUAL_ENV", str(active))
        monkeypatch.chdir(project)
        info = TargetResolver().resolve(None)
        assert info.site_packages == active
        assert info.config_dir == project

    def test_project_venv_beats_activated_virtualenv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        venv = _make_venv(tmp_path / ".venv")
        monkeypatch.setenv("VIRTUAL_ENV", str(_make_venv(tmp_path / "other")))
        monkeypatch.chdir(tmp_path)
        assert TargetResolver().resolve(None).site_packages == venv

    def test_stale_virtual_env_falls_back_to_running_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "deleted"))
        monkeypatch.chdir(tmp_path)
        assert TargetResolver().resolve(None).site_packages is None

    def test_cwd_venv_wins_over_enclosing_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A directory with its own .venv (a requirements.txt project inside
        a larger repository) is audited as before."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "outer"\n')
        tool = tmp_path / "tools" / "script"
        venv = _make_venv(tool / ".venv")
        monkeypatch.chdir(tool)
        info = TargetResolver().resolve(None)
        assert info.site_packages == venv
        assert info.config_dir == tool
