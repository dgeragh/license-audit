"""Tests for environment analysis."""

from pathlib import Path

import pytest

from license_audit.environment.analyze import analyze_environment


class TestAnalyzeEnvironment:
    def test_own_venv(self) -> None:
        """Analyze license_audit's own .venv."""
        venv_path = Path(__file__).parents[3] / ".venv"
        if not venv_path.exists():
            pytest.skip(".venv not found")
        # Find site-packages
        sp = None
        for child in (venv_path / "lib").iterdir():
            candidate = child / "site-packages"
            if candidate.is_dir():
                sp = candidate
                break
        if sp is None:
            pytest.skip("site-packages not found")

        tree = analyze_environment("license_audit", sp)
        packages = tree.flatten()
        assert len(packages) > 0
        names = {p.name for p in packages}
        assert "click" in names

    def test_detects_licenses(self) -> None:
        """License detection should work for installed packages."""
        venv_path = Path(__file__).parents[3] / ".venv"
        if not venv_path.exists():
            pytest.skip(".venv not found")
        sp = None
        for child in (venv_path / "lib").iterdir():
            candidate = child / "site-packages"
            if candidate.is_dir():
                sp = candidate
                break
        if sp is None:
            pytest.skip("site-packages not found")

        tree = analyze_environment("license_audit", sp)
        packages = tree.flatten()
        # click should have a detected license
        click_pkgs = [p for p in packages if p.name == "click"]
        assert len(click_pkgs) == 1
        assert click_pkgs[0].license_expression != "UNKNOWN"

    def test_overrides_applied(self) -> None:
        """Overrides should take precedence."""
        venv_path = Path(__file__).parents[3] / ".venv"
        if not venv_path.exists():
            pytest.skip(".venv not found")
        sp = None
        for child in (venv_path / "lib").iterdir():
            candidate = child / "site-packages"
            if candidate.is_dir():
                sp = candidate
                break
        if sp is None:
            pytest.skip("site-packages not found")

        tree = analyze_environment(
            "license_audit", sp, overrides={"click": "custom-license"}
        )
        packages = tree.flatten()
        click_pkgs = [p for p in packages if p.name == "click"]
        assert click_pkgs[0].license_expression == "custom-license"
