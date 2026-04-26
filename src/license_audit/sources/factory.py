"""Build the right Source for a given dependency file."""

from __future__ import annotations

from pathlib import Path

from license_audit.sources.base import Source
from license_audit.sources.pixi_lock import PixiLockSource
from license_audit.sources.poetry_lock import PoetryLockSource
from license_audit.sources.pyproject import PyprojectSource
from license_audit.sources.requirements import RequirementsSource
from license_audit.sources.uv_lock import UvLockSource


class SourceFactory:
    """Picks the right Source subclass for a dependency file."""

    LOCK_FILES: tuple[str, ...] = ("uv.lock", "poetry.lock", "pixi.lock")

    # Search order for auto-detection: first hit wins. Lock files come first
    # because they're more specific and have transitive resolution; uv.lock
    # remains the top default for dogfood/test compatibility.
    PROJECT_FILES: tuple[str, ...] = (
        "uv.lock",
        "poetry.lock",
        "pixi.lock",
        "requirements.txt",
        "pyproject.toml",
    )

    def create(self, path: Path, groups: list[str] | None = None) -> Source:
        """Instantiate a Source for `path`, or raise ValueError if unrecognized."""
        name = path.name.lower()
        if name == "uv.lock":
            return UvLockSource(path, groups=groups)
        if name == "poetry.lock":
            return PoetryLockSource(path, groups=groups)
        if name == "pixi.lock":
            return PixiLockSource(path, groups=groups)
        if self._is_requirements(name):
            return RequirementsSource(path, groups=groups)
        if name == "pyproject.toml":
            return PyprojectSource(path, groups=groups)
        msg = f"Unrecognized dependency file: {path.name}"
        raise ValueError(msg)

    def validate(self, path: Path) -> None:
        """Raise ValueError if `path` isn't a recognized dependency file."""
        name = path.name.lower()
        if name in self.LOCK_FILES or name == "pyproject.toml":
            return
        if self._is_requirements(name):
            return
        msg = f"Unrecognized dependency file: {path.name}"
        raise ValueError(msg)

    def detect_in_project_dir(self, project_dir: Path) -> Path | None:
        """First recognized dependency file in `project_dir`, or None."""
        for filename in self.PROJECT_FILES:
            candidate = project_dir / filename
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _is_requirements(name: str) -> bool:
        return name.startswith("requirements") and name.endswith(".txt")
