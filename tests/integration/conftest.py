"""Shared fixtures for integration tests.

These build a fake virtualenv on disk (a ``site-packages`` populated with
``*.dist-info/METADATA``) so the full pipeline runs against a real installed
layout without any network access or `pip install` step.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


def _write_dist_info(
    site_packages: Path,
    name: str,
    version: str,
    license_expression: str,
) -> None:
    dist_info = site_packages / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.4\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        f"License-Expression: {license_expression}\n"
    )


@pytest.fixture
def make_venv() -> Callable[[Path, dict[str, str]], Path]:
    """Return a builder that writes a fake virtualenv at a path.

    Pass a ``{name: license_expression}`` mapping; each becomes an installed
    package the auditor can read.
    """

    def _build(root: Path, packages: dict[str, str]) -> Path:
        site_packages = root / "lib" / "python3.12" / "site-packages"
        site_packages.mkdir(parents=True)
        for name, license_expression in packages.items():
            _write_dist_info(site_packages, name, "1.0.0", license_expression)
        return root

    return _build
