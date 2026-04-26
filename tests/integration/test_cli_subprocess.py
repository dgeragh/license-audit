"""End-to-end subprocess tests for the license-audit CLI.

These tests run the installed ``license-audit`` console script as a real
subprocess so they catch what in-process ``CliRunner`` tests can't:

- The ``[project.scripts]`` entry point actually wires up.
- Real OS exit codes propagate through the process boundary.
- Stdout / stderr separation works under shell-style invocation.
- JSON output is parseable by an external interpreter.
- ``warnings.warn`` from inside the analyzer reaches the user's stderr.

Each test provisions a synthetic project under ``tmp_path``. The provisioning
step (``uv pip install`` of small real packages) makes these noticeably slower
than the unit suite, hence their separate location under ``tests/integration``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _binary() -> str:
    """Resolve the ``license-audit`` executable path."""
    path = shutil.which("license-audit")
    if path is None:
        pytest.skip("license-audit binary not on PATH")
    return path


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``license-audit`` and return the completed process. Never raises on non-zero."""
    return subprocess.run(
        [_binary(), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _make_pyproject(
    path: Path,
    *,
    deps: list[str] | None = None,
    overrides: dict[str, str] | None = None,
    ignored: dict[str, str] | None = None,
    allowed: list[str] | None = None,
    denied: list[str] | None = None,
    policy: str | None = None,
) -> None:
    """Write a synthetic pyproject.toml with the requested config."""
    lines = [
        "[project]",
        'name = "synthetic"',
        'version = "0.0.1"',
    ]
    if deps:
        deps_repr = ", ".join(f'"{d}"' for d in deps)
        lines.append(f"dependencies = [{deps_repr}]")
    if any(x is not None for x in (allowed, denied, policy)):
        lines.append("[tool.license-audit]")
        if policy:
            lines.append(f'policy = "{policy}"')
        if allowed:
            allowed_repr = ", ".join(f'"{a}"' for a in allowed)
            lines.append(f"allowed-licenses = [{allowed_repr}]")
        if denied:
            denied_repr = ", ".join(f'"{d}"' for d in denied)
            lines.append(f"denied-licenses = [{denied_repr}]")
    if overrides:
        lines.append("[tool.license-audit.overrides]")
        for k, v in overrides.items():
            lines.append(f'{k} = "{v}"')
    if ignored:
        lines.append("[tool.license-audit.ignored-packages]")
        for k, v in ignored.items():
            lines.append(f'{k} = "{v}"')
    path.write_text("\n".join(lines) + "\n")


# -----------------------------------------------------------------------------
# Console-script wiring
# -----------------------------------------------------------------------------


class TestEntryPoint:
    def test_version_runs_and_exits_zero(self) -> None:
        result = _run(["--version"])
        assert result.returncode == 0
        assert "license-audit, version" in result.stdout

    def test_help_runs_and_exits_zero(self) -> None:
        result = _run(["--help"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# -----------------------------------------------------------------------------
# Exit-code contract via real process boundary
# -----------------------------------------------------------------------------


class TestExitCodes:
    def test_clean_check_exits_zero(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path / "pyproject.toml", deps=["click>=8.1.0"])
        result = _run(["--target", str(tmp_path), "check"])
        assert result.returncode == 0, result.stdout + result.stderr

    def test_policy_violation_exits_one(self, tmp_path: Path) -> None:
        _make_pyproject(
            tmp_path / "pyproject.toml",
            deps=["click>=8.1.0"],
            policy="permissive",
            overrides={"click": "GPL-3.0-only"},
        )
        result = _run(["--target", str(tmp_path), "check"])
        assert result.returncode == 1

    def test_unknown_license_with_fail_on_unknown_exits_two(
        self, tmp_path: Path
    ) -> None:
        _make_pyproject(
            tmp_path / "pyproject.toml",
            deps=["click>=8.1.0"],
            overrides={"click": "PROPRIETARY-NOT-A-REAL-SPDX"},
        )
        result = _run(["--target", str(tmp_path), "check", "--fail-on-unknown"])
        assert result.returncode == 2

    def test_unknown_license_with_no_fail_on_unknown_exits_zero(
        self, tmp_path: Path
    ) -> None:
        _make_pyproject(
            tmp_path / "pyproject.toml",
            deps=["click>=8.1.0"],
            overrides={"click": "PROPRIETARY-NOT-A-REAL-SPDX"},
        )
        result = _run(["--target", str(tmp_path), "check", "--no-fail-on-unknown"])
        assert result.returncode == 0


# -----------------------------------------------------------------------------
# JSON output parseable by external interpreter
# -----------------------------------------------------------------------------


class TestJsonOutputs:
    def test_analyze_json_parses_and_has_expected_shape(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path / "pyproject.toml", deps=["click>=8.1.0"])
        result = _run(["--target", str(tmp_path), "analyze", "--format", "json"])
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert "packages" in payload
        assert "policy_passed" in payload
        assert any(p["name"] == "click" for p in payload["packages"])

    def test_report_json_parses(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path / "pyproject.toml", deps=["click>=8.1.0"])
        result = _run(["--target", str(tmp_path), "report", "--format", "json"])
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert {"packages", "policy_passed", "metadata"}.issubset(payload.keys())

    def test_report_output_writes_file(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path / "pyproject.toml", deps=["click>=8.1.0"])
        out = tmp_path / "out.json"
        result = _run([
            "--target",
            str(tmp_path),
            "report",
            "--format",
            "json",
            "--output",
            str(out),
        ])
        assert result.returncode == 0
        assert out.exists() and out.stat().st_size > 0
        json.loads(out.read_text())  # parses


# -----------------------------------------------------------------------------
# pixi conda warning surfaces through CLI to stderr
# -----------------------------------------------------------------------------


_PIXI_WITH_CONDA = """\
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
  sha256: deadbeef
"""


class TestPixiCondaWarningSurfaces:
    def test_conda_skip_warning_appears_on_stderr(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path / "pyproject.toml")
        (tmp_path / "pixi.lock").write_text(_PIXI_WITH_CONDA)
        result = _run(["--target", str(tmp_path / "pixi.lock"), "analyze"])
        assert result.returncode == 0
        assert "conda package" in result.stderr
