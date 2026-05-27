"""Attach to or create the Python environment we audit."""

from __future__ import annotations

import atexit
import logging
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from rich.console import Console
from rich.status import Status

from license_audit.sources.base import PackageSpec
from license_audit.util import MetadataReader

logger = logging.getLogger(__name__)


@dataclass
class ProvisionedEnv:
    """A reader bound to whichever environment we provisioned.

    Use as a context manager so temp directories get cleaned up.
    """

    reader: MetadataReader
    _tmp_dir: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    def cleanup(self) -> None:
        """Remove the temporary environment if one was created."""
        if self._tmp_dir is not None:
            atexit.unregister(self._tmp_dir.cleanup)
            self._tmp_dir.cleanup()
            self._tmp_dir = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.cleanup()


class EnvironmentProvisioner:
    """Creates or attaches to the Python environment we analyze."""

    _PYPI_FALLBACK_URL = "https://pypi.org/simple"

    def __init__(self, console: Console | None = None) -> None:
        # Spinner output goes to stderr so stdout (e.g. piped JSON) stays clean.
        self._console = console or Console(stderr=True)

    def current(self) -> ProvisionedEnv:
        """Use the interpreter running license_audit itself."""
        site_packages = Path(sysconfig.get_path("purelib"))
        return ProvisionedEnv(reader=MetadataReader.from_site_packages(site_packages))

    def from_venv(self, venv_path: Path) -> ProvisionedEnv:
        """Attach to an existing virtualenv at `venv_path`.

        Raises FileNotFoundError when no site-packages directory is found.
        """
        sp = self._find_site_packages(venv_path)
        if sp is None:
            msg = f"No site-packages directory found in {venv_path}"
            raise FileNotFoundError(msg)
        return ProvisionedEnv(reader=MetadataReader.from_site_packages(sp))

    def temp(self, specs: list[PackageSpec]) -> ProvisionedEnv:
        """Resolve `specs` into a temp directory of ``.whl`` files via ``pip wheel``.

        Wheels are downloaded where available and built from sdist
        otherwise (PEP 517). atexit cleanup is registered before pip
        runs so a crash mid-provision doesn't leak the temp dir.
        """
        tmp_dir = tempfile.TemporaryDirectory(prefix="license_audit_")
        atexit.register(tmp_dir.cleanup)

        try:
            wheel_dir = Path(tmp_dir.name) / "wheels"
            wheel_dir.mkdir()
            label = self._provision_label(specs)
            with self._console.status(label, spinner="dots") as status:
                self._download_wheels(specs, wheel_dir, status)
        except subprocess.CalledProcessError as e:
            atexit.unregister(tmp_dir.cleanup)
            tmp_dir.cleanup()
            msg = (
                f"Failed to provision environment: {e.stderr or e.stdout or str(e)}\n"
                "Check your network connection and that all packages exist on PyPI."
            )
            raise RuntimeError(msg) from e
        except BaseException:
            atexit.unregister(tmp_dir.cleanup)
            tmp_dir.cleanup()
            raise

        return ProvisionedEnv(
            reader=MetadataReader.from_wheel_dir(wheel_dir),
            _tmp_dir=tmp_dir,
        )

    def is_venv_dir(self, path: Path) -> bool:
        """True if `path` looks like a virtualenv: site-packages present, no pyproject."""
        if not path.is_dir():
            return False
        if (path / "pyproject.toml").exists():
            return False
        return self._find_site_packages(path) is not None

    def _download_wheels(
        self,
        specs: list[PackageSpec],
        wheel_dir: Path,
        status: Status,
    ) -> None:
        if not specs:
            return

        groups: dict[str, list[PackageSpec]] = {}
        for spec in specs:
            groups.setdefault(spec.index_url, []).append(spec)

        for index_url, group_specs in groups.items():
            base_cmd = self._build_base_cmd(wheel_dir, index_url)
            self._download_group(base_cmd, group_specs, status)

    def _download_group(
        self,
        base_cmd: list[str],
        specs: list[PackageSpec],
        status: Status,
    ) -> None:
        install_args = [self._spec_to_install_arg(s) for s in specs]

        result = self._run_pip(base_cmd, install_args)
        if result.returncode == 0:
            return

        # Retry one spec at a time so a single yanked or unpublished version doesn't
        # kill the rest.
        logger.debug("Batch wheel build failed, falling back to individual builds")
        for index, spec in enumerate(specs, start=1):
            arg = self._spec_to_install_arg(spec)
            status.update(
                f"Resolving package by package ({index}/{len(specs)}): {spec.name}…"
            )
            per_pkg = self._run_pip(base_cmd, [arg])
            if per_pkg.returncode == 0:
                continue
            fallback = self._run_pip(base_cmd, [spec.name])
            if fallback.returncode != 0:
                logger.warning(
                    "Could not build wheel for '%s', skipping "
                    "(license info will be unavailable)",
                    arg,
                )
            else:
                logger.warning(
                    "Exact version %s not available; "
                    "built latest release instead (license may differ)",
                    arg,
                )

    @staticmethod
    def _provision_label(specs: list[PackageSpec]) -> str:
        n = len(specs)
        suffix = "" if n == 1 else "s"
        return f"Provisioning {n} top-level package{suffix} via pip wheel…"

    @staticmethod
    def _run_pip(
        base_cmd: list[str],
        extra_args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*base_cmd, *extra_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    @staticmethod
    def _spec_to_install_arg(spec: PackageSpec) -> str:
        """Format a PackageSpec as a positional arg for `pip wheel`."""
        if spec.source_url:
            return f"{spec.name} @ {spec.source_url}"
        return f"{spec.name}{spec.version_constraint}"

    @staticmethod
    def _build_base_cmd(wheel_dir: Path, index_url: str) -> list[str]:
        """Build the `pip wheel` base command for a given index URL."""
        cmd = [sys.executable, "-m", "pip", "wheel", "--pre", "-w", str(wheel_dir)]
        if index_url:
            cmd.extend(["--index-url", index_url])
            cmd.extend(["--extra-index-url", EnvironmentProvisioner._PYPI_FALLBACK_URL])
        return cmd

    @staticmethod
    def _find_site_packages(venv_path: Path) -> Path | None:
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
