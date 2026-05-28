"""Tests for the LicenseAuditor orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.core.analyzer import LicenseAuditor, TargetInfo
from license_audit.core.models import (
    UNKNOWN_LICENSE,
    LicenseCategory,
    PackageLicense,
)


class TestRun:
    def test_self_analysis(self) -> None:
        """Analyze license-audit's own dependencies via its .venv."""
        project_dir = Path(__file__).parents[2]
        if not (project_dir / ".venv").exists():
            pytest.skip(".venv not found")
        report = LicenseAuditor().run(target=project_dir)
        assert report.project_name == "license-audit"
        assert len(report.packages) > 0
        assert report.policy_passed is not None
        assert ".venv" in report.source

    def test_project_without_venv_raises(self, tmp_path: Path) -> None:
        """A directory with no virtualenv raises FileNotFoundError."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        with pytest.raises(FileNotFoundError):
            LicenseAuditor().run(target=tmp_path)

    def test_no_target_uses_current_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        report = LicenseAuditor().run()
        assert report.project_name is not None
        assert report.source == "active environment"

    def test_config_dir_overrides_project_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--config location supplies the project name, not the target's."""
        project = tmp_path / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text('[project]\nname = "from-config"\n')
        monkeypatch.chdir(tmp_path)
        report = LicenseAuditor().run(config_dir=project)
        assert report.project_name == "from-config"


class TestDescribeSource:
    def test_site_packages_wins(self, tmp_path: Path) -> None:
        info = TargetInfo(site_packages=tmp_path / ".venv", config_dir=tmp_path)
        assert LicenseAuditor._describe_source(info) == str(tmp_path / ".venv")

    def test_active_environment_fallback(self) -> None:
        assert LicenseAuditor._describe_source(TargetInfo()) == "active environment"


class TestClassifyPackage:
    def test_single_license(self) -> None:
        pkg = PackageLicense(name="a", version="1.0", license_expression="MIT")
        auditor = LicenseAuditor()
        auditor._classify_package(pkg)
        assert pkg.category == LicenseCategory.PERMISSIVE

    def test_or_expression_picks_most_permissive(self) -> None:
        pkg = PackageLicense(
            name="a",
            version="1.0",
            license_expression="MIT OR GPL-3.0-only",
        )
        auditor = LicenseAuditor()
        auditor._classify_package(pkg)
        assert pkg.category == LicenseCategory.PERMISSIVE

    def test_and_expression_picks_most_restrictive(self) -> None:
        pkg = PackageLicense(
            name="tqdm",
            version="4.67",
            license_expression="MPL-2.0 AND MIT",
        )
        auditor = LicenseAuditor()
        auditor._classify_package(pkg)
        assert pkg.category == LicenseCategory.WEAK_COPYLEFT

    def test_nested_and_over_or(self) -> None:
        pkg = PackageLicense(
            name="orjson",
            version="3.11",
            license_expression="MPL-2.0 AND (Apache-2.0 OR MIT)",
        )
        auditor = LicenseAuditor()
        auditor._classify_package(pkg)
        assert pkg.category == LicenseCategory.WEAK_COPYLEFT


class TestExtractSpdxIds:
    def test_skips_unknown(self) -> None:
        auditor = LicenseAuditor()
        result = auditor._extract_spdx_ids(["MIT", UNKNOWN_LICENSE, "Apache-2.0"])
        assert "MIT" in result
        assert "Apache-2.0" in result
        assert UNKNOWN_LICENSE not in result

    def test_empty_list(self) -> None:
        assert LicenseAuditor()._extract_spdx_ids([]) == []

    def test_or_expression_only_contributes_chosen_branch(self) -> None:
        result = LicenseAuditor()._extract_spdx_ids(["GPL-3.0-only OR MIT"])
        assert "MIT" in result
        assert "GPL-3.0-only" not in result

    def test_and_expression_contributes_all_components(self) -> None:
        result = LicenseAuditor()._extract_spdx_ids(["MPL-2.0 AND MIT"])
        assert "MPL-2.0" in result
        assert "MIT" in result
