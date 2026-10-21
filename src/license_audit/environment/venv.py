"""Locate the site-packages of the environment we audit."""

from __future__ import annotations

import re
import sysconfig
from pathlib import Path

from license_audit.util import MetadataReader

_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")


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
    return MetadataReader.from_site_packages(sp, marker_environment(venv_path, sp))


def marker_environment(venv_path: Path, site_packages: Path) -> dict[str, str]:
    """Marker values for the virtualenv where they can differ from ours.

    Only the Python version is read, from pyvenv.cfg or else the
    `lib/pythonX.Y` directory name; platform markers are the host's, since a
    virtualenv runs on the machine that holds it. Empty when unknown.
    """
    version = _pyvenv_version(venv_path / "pyvenv.cfg")
    if version is None:
        match = _VERSION.search(site_packages.parent.name)
        version = match.group() if match else None
    if version is None:
        return {}
    major_minor = ".".join(version.split(".")[:2])
    return {"python_version": major_minor, "python_full_version": version}


def _pyvenv_version(cfg: Path) -> str | None:
    """Python version a pyvenv.cfg records (`version_info` or `version`)."""
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip().lower()] = value.strip()
    for key in ("version_info", "version"):
        match = _VERSION.match(values.get(key, ""))
        if match:
            return match.group()
    return None


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
