"""Locate the site-packages of the environment we audit."""

from __future__ import annotations

import sysconfig
from pathlib import Path

from license_audit.util import MetadataReader


def current_reader() -> MetadataReader:
    """Reader for the interpreter running license_audit itself."""
    site_packages = Path(sysconfig.get_path("purelib"))
    return MetadataReader.from_site_packages(site_packages)


def reader_for_venv(venv_path: Path) -> MetadataReader:
    """Reader for an existing virtualenv at `venv_path`.

    Raises FileNotFoundError when no site-packages directory is found.
    """
    sp = find_site_packages(venv_path)
    if sp is None:
        msg = f"No site-packages directory found in {venv_path}"
        raise FileNotFoundError(msg)
    return MetadataReader.from_site_packages(sp)


def is_venv_dir(path: Path) -> bool:
    """True if `path` looks like a virtualenv: site-packages present, no pyproject."""
    if not path.is_dir():
        return False
    if (path / "pyproject.toml").exists():
        return False
    return find_site_packages(path) is not None


def find_site_packages(venv_path: Path) -> Path | None:
    """Locate the site-packages dir inside a virtualenv, or None."""
    lib_dir = venv_path / "lib"
    if lib_dir.is_dir():
        for child in lib_dir.iterdir():
            sp = child / "site-packages"
            if sp.is_dir():
                return sp

    sp = venv_path / "Lib" / "site-packages"
    if sp.is_dir():
        return sp

    return None
