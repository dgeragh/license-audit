"""End-to-end ``LicenseAuditor`` tests with real provisioning.

These tests run the unmocked auditor against synthetic ``tmp_path`` projects
covering every source format. They verify the spec to ``uv pip install`` to
metadata read to report flow per format, plus that config (overrides, ignored,
groups) reaches the produced ``AnalysisReport``.

Slower than unit tests because each invocation provisions a small temp
environment via uv. Lives in ``tests/integration`` so the unit suite stays fast.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from license_audit.config import LicenseAuditConfig
from license_audit.core.analyzer import LicenseAuditor


def _write_pyproject(path: Path, body: str) -> None:
    path.write_text(body)


# -----------------------------------------------------------------------------
# Source format coverage: each format provisions and produces a report
# -----------------------------------------------------------------------------


class TestSourceFormats:
    def test_pyproject_only(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        names = {p.name for p in report.packages}
        assert "click" in names

    def test_requirements_txt(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("click>=8.1.0\n")
        report = LicenseAuditor().run(target=tmp_path / "requirements.txt")
        names = {p.name for p in report.packages}
        assert "click" in names

    def test_poetry_lock(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        (tmp_path / "poetry.lock").write_text("""\
[[package]]
name = "click"
version = "8.1.7"
optional = false
python-versions = ">=3.7"
groups = ["main"]
files = []

[[package]]
name = "pytest"
version = "8.3.3"
optional = false
python-versions = ">=3.8"
groups = ["dev"]
files = []

[metadata]
lock-version = "2.1"
python-versions = ">=3.10"
content-hash = "x"
""")
        report = LicenseAuditor().run(target=tmp_path / "poetry.lock")
        names = {p.name for p in report.packages}
        assert {"click", "pytest"}.issubset(names)

    def test_poetry_lock_with_main_group_filter(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        (tmp_path / "poetry.lock").write_text("""\
[[package]]
name = "click"
version = "8.1.7"
optional = false
python-versions = ">=3.7"
groups = ["main"]
files = []

[[package]]
name = "pytest"
version = "8.3.3"
optional = false
python-versions = ">=3.8"
groups = ["dev"]
files = []

[metadata]
lock-version = "2.1"
python-versions = ">=3.10"
content-hash = "x"
""")
        config = LicenseAuditConfig(dependency_groups=["main"])
        report = LicenseAuditor().run(target=tmp_path / "poetry.lock", config=config)
        names = {p.name for p in report.packages}
        assert "click" in names
        assert "pytest" not in names

    def test_pixi_lock_pypi_only(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        (tmp_path / "pixi.lock").write_text("""\
version: 6
environments:
  default:
    channels:
    - url: https://conda.anaconda.org/conda-forge/
    indexes:
    - https://pypi.org/simple
    packages:
      linux-64:
      - conda: https://conda.anaconda.org/conda-forge/linux-64/python-3.12.0-x.conda
      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
      linux-aarch64:
      - conda: https://conda.anaconda.org/conda-forge/linux-aarch64/python-3.12.0-x.conda
      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
      osx-64:
      - conda: https://conda.anaconda.org/conda-forge/osx-64/python-3.12.0-x.conda
      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
      osx-arm64:
      - conda: https://conda.anaconda.org/conda-forge/osx-arm64/python-3.12.0-x.conda
      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
      win-64:
      - conda: https://conda.anaconda.org/conda-forge/win-64/python-3.12.0-x.conda
      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
packages:
- conda: https://conda.anaconda.org/conda-forge/linux-64/python-3.12.0-x.conda
  name: python
  version: 3.12.0
  build: x
  subdir: linux-64
- pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
  name: click
  version: 8.1.7
  sha256: testhash
""")
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            report = LicenseAuditor().run(target=tmp_path / "pixi.lock")
        names = {p.name for p in report.packages}
        assert "click" in names
        # Conda packages are skipped; the warning is what surfaces them.
        assert any("conda" in str(w.message) for w in captured)


# -----------------------------------------------------------------------------
# Config flows from pyproject.toml through analyzer to report
# -----------------------------------------------------------------------------


class TestConfigPropagation:
    def test_override_applied_to_package(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n'
            "[tool.license-audit.overrides]\n"
            'click = "Apache-2.0"\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        click = next(p for p in report.packages if p.name == "click")
        # Override should swap click's actual BSD-3-Clause license for Apache-2.0.
        assert click.license_expression == "Apache-2.0"

    def test_ignored_package_marked_in_report(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n'
            "[tool.license-audit.ignored-packages]\n"
            'click = "Smoke test exemption"\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        click = next(p for p in report.packages if p.name == "click")
        assert click.ignored is True
        assert click.ignore_reason == "Smoke test exemption"

    def test_denied_license_fails_policy(self, tmp_path: Path) -> None:
        # click ships as BSD-3-Clause; deny it.
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n'
            "[tool.license-audit]\n"
            'denied-licenses = ["BSD-3-Clause"]\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is False

    def test_allowed_licenses_pass_when_matching(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n'
            "[tool.license-audit]\n"
            'allowed-licenses = ["BSD-3-Clause"]\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is True

    def test_allowed_licenses_fail_when_not_matching(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n'
            "[tool.license-audit]\n"
            'allowed-licenses = ["MIT"]\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is False

    @pytest.mark.parametrize(
        "policy,expected_pass",
        [
            ("permissive", False),
            ("weak-copyleft", True),
            ("strong-copyleft", True),
            ("network-copyleft", True),
        ],
    )
    def test_policy_level_graduation(
        self, tmp_path: Path, policy: str, expected_pass: bool
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            'dependencies = ["click>=8.1.0"]\n'
            "[tool.license-audit]\n"
            f'policy = "{policy}"\n'
            "[tool.license-audit.overrides]\n"
            'click = "MPL-2.0"\n',
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is expected_pass
