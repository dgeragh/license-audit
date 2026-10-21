"""Tests for environment discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.environment.venv import (
    current_reader,
    find_site_packages,
    is_venv_dir,
    marker_environment,
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


class TestMarkerEnvironment:
    @pytest.mark.parametrize(
        ("cfg", "expected"),
        [
            ("home = /usr/bin\nversion_info = 3.13.2\n", "3.13.2"),  # uv
            ("home = /usr/bin\nversion = 3.11.9\n", "3.11.9"),  # venv
            ("version_info = 3.12.4.final.0\n", "3.12.4"),  # virtualenv
            ("Version = 3.10.1\n", "3.10.1"),
        ],
    )
    def test_reads_pyvenv_cfg(self, tmp_path: Path, cfg: str, expected: str) -> None:
        venv = _make_venv(tmp_path)
        (venv / "pyvenv.cfg").write_text(cfg)
        sp = find_site_packages(venv)
        assert sp is not None
        env = marker_environment(venv, sp)
        assert env == {
            "python_version": ".".join(expected.split(".")[:2]),
            "python_full_version": expected,
        }

    def test_falls_back_to_lib_directory(self, tmp_path: Path) -> None:
        sp = tmp_path / "lib" / "python3.13t" / "site-packages"
        sp.mkdir(parents=True)
        assert marker_environment(tmp_path, sp) == {
            "python_version": "3.13",
            "python_full_version": "3.13",
        }

    def test_unknown_version_keeps_ours(self, tmp_path: Path) -> None:
        sp = tmp_path / "Lib" / "site-packages"
        sp.mkdir(parents=True)
        (tmp_path / "pyvenv.cfg").write_text("home = C:\\Python\nversion = ?\n")
        assert marker_environment(tmp_path, sp) == {}

    def test_reader_for_venv_carries_it(self, tmp_path: Path) -> None:
        venv = _make_venv(tmp_path)
        assert reader_for_venv(venv).marker_environment["python_version"] == "3.12"
