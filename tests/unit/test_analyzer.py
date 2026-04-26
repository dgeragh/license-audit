"""Tests for the LicenseAuditor orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.core.analyzer import LicenseAuditor
from license_audit.core.models import (
    UNKNOWN_LICENSE,
    LicenseCategory,
    PackageLicense,
)


class TestRun:
    def test_self_analysis(self) -> None:
        """Analyze license-audit's own dependencies via its .venv."""
        project_dir = Path(__file__).parents[2]
        report = LicenseAuditor().run(target=project_dir)
        assert report.project_name == "license-audit"
        assert len(report.packages) > 0
        assert report.policy_passed is not None

    def test_unknown_project(self, tmp_path: Path) -> None:
        """Empty directory with no source files raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            LicenseAuditor().run(target=tmp_path)

    def test_no_target_uses_current_env(self) -> None:
        report = LicenseAuditor().run()
        assert report.project_name is not None


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


class TestExtractSpdxIds:
    def test_skips_unknown(self) -> None:
        auditor = LicenseAuditor()
        result = auditor._extract_spdx_ids(["MIT", UNKNOWN_LICENSE, "Apache-2.0"])
        assert "MIT" in result
        assert "Apache-2.0" in result
        assert UNKNOWN_LICENSE not in result

    def test_empty_list(self) -> None:
        assert LicenseAuditor()._extract_spdx_ids([]) == []
