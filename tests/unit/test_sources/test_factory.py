"""Tests for SourceFactory."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.sources.factory import SourceFactory
from license_audit.sources.pyproject import PyprojectSource
from license_audit.sources.requirements import RequirementsSource
from license_audit.sources.uv_lock import UvLockSource


class TestCreate:
    def test_uv_lock(self, tmp_path: Path) -> None:
        lock = tmp_path / "uv.lock"
        lock.write_text("version = 1\n")
        source = SourceFactory().create(lock)
        assert isinstance(source, UvLockSource)

    def test_pyproject_with_groups(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\ndependencies = ["click"]\n')
        source = SourceFactory().create(pyproject, groups=["main"])
        assert isinstance(source, PyprojectSource)

    def test_requirements_variant(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements-dev.txt"
        req.write_text("pytest\n")
        source = SourceFactory().create(req)
        assert isinstance(source, RequirementsSource)

    def test_unknown_filename_raises(self, tmp_path: Path) -> None:
        unknown = tmp_path / "deps.yaml"
        unknown.write_text("")
        with pytest.raises(ValueError, match="Unrecognized dependency file"):
            SourceFactory().create(unknown)


class TestValidate:
    def test_uv_lock(self, tmp_path: Path) -> None:
        SourceFactory().validate(tmp_path / "uv.lock")

    def test_pyproject(self, tmp_path: Path) -> None:
        SourceFactory().validate(tmp_path / "pyproject.toml")

    def test_requirements_variant(self, tmp_path: Path) -> None:
        SourceFactory().validate(tmp_path / "requirements-test.txt")

    def test_unknown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unrecognized dependency file"):
            SourceFactory().validate(tmp_path / "deps.yaml")


class TestDetectInProjectDir:
    def test_prefers_uv_lock(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
        (tmp_path / "requirements.txt").write_text("")
        (tmp_path / "uv.lock").write_text("version = 1\n")
        found = SourceFactory().detect_in_project_dir(tmp_path)
        assert found is not None
        assert found.name == "uv.lock"

    def test_requirements_over_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
        (tmp_path / "requirements.txt").write_text("")
        found = SourceFactory().detect_in_project_dir(tmp_path)
        assert found is not None
        assert found.name == "requirements.txt"

    def test_returns_none_when_no_source(self, tmp_path: Path) -> None:
        assert SourceFactory().detect_in_project_dir(tmp_path) is None
