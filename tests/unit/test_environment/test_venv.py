"""Tests for environment discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.environment.venv import (
    current_reader,
    find_site_packages,
    is_venv_dir,
    reader_for_venv,
)


def _make_venv(path: Path) -> Path:
    (path / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    return path


class TestCurrentReader:
    def test_points_at_site_packages(self) -> None:
        reader = current_reader()
        described = Path(reader.describe_source())
        assert described.exists()
        assert "site-packages" in str(described)


class TestReaderForVenv:
    def test_own_venv(self) -> None:
        venv_path = Path(__file__).parents[3] / ".venv"
        if not venv_path.exists():
            pytest.skip(".venv not found")
        reader = reader_for_venv(venv_path)
        described = Path(reader.describe_source())
        assert described.exists()
        assert any(described.glob("*.dist-info"))

    def test_missing_venv(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            reader_for_venv(tmp_path / "nonexistent")


class TestIsVenvDir:
    def test_synthetic_venv(self, tmp_path: Path) -> None:
        assert is_venv_dir(_make_venv(tmp_path))

    def test_dir_with_pyproject_is_not_venv(self, tmp_path: Path) -> None:
        _make_venv(tmp_path)
        (tmp_path / "pyproject.toml").write_text("")
        assert not is_venv_dir(tmp_path)

    def test_nonexistent_is_not_venv(self, tmp_path: Path) -> None:
        assert not is_venv_dir(tmp_path / "nonexistent")


class TestFindSitePackages:
    def test_unix_layout(self, tmp_path: Path) -> None:
        sp = tmp_path / "lib" / "python3.12" / "site-packages"
        sp.mkdir(parents=True)
        assert find_site_packages(tmp_path) == sp

    def test_windows_layout(self, tmp_path: Path) -> None:
        sp = tmp_path / "Lib" / "site-packages"
        sp.mkdir(parents=True)
        assert find_site_packages(tmp_path) == sp

    def test_missing_returns_none(self, tmp_path: Path) -> None:
        assert find_site_packages(tmp_path) is None
