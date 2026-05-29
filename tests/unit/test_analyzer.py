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


class TestApplyClassifications:
    def _unrecognized(self, name: str = "gpu") -> PackageLicense:
        return PackageLicense(
            name=name,
            version="1.0",
            license_expression=UNKNOWN_LICENSE,
            declared_license="Proprietary License",
            category=LicenseCategory.UNKNOWN,
        )

    def test_assigns_category_and_marks_overridden(self) -> None:
        pkg = self._unrecognized()
        LicenseAuditor._apply_classifications(
            [pkg], {"Proprietary License": "permissive"}
        )
        assert pkg.category == LicenseCategory.PERMISSIVE
        assert pkg.category_overridden is True
        # The expression stays the sentinel so SPDX-based steps skip it.
        assert pkg.license_expression == UNKNOWN_LICENSE

    def test_matches_case_insensitively(self) -> None:
        pkg = self._unrecognized()
        LicenseAuditor._apply_classifications(
            [pkg], {"proprietary license": "permissive"}
        )
        assert pkg.category == LicenseCategory.PERMISSIVE

    def test_one_entry_covers_all_occurrences(self) -> None:
        pkgs = [self._unrecognized("a"), self._unrecognized("b")]
        LicenseAuditor._apply_classifications(
            pkgs, {"Proprietary License": "permissive"}
        )
        assert all(p.category == LicenseCategory.PERMISSIVE for p in pkgs)

    def test_non_matching_package_untouched(self) -> None:
        pkg = self._unrecognized()
        LicenseAuditor._apply_classifications(
            [pkg], {"Some Other License": "permissive"}
        )
        assert pkg.category == LicenseCategory.UNKNOWN
        assert pkg.category_overridden is False

    def test_empty_config_is_noop(self) -> None:
        pkg = self._unrecognized()
        LicenseAuditor._apply_classifications([pkg], {})
        assert pkg.category == LicenseCategory.UNKNOWN

    def test_matches_whitespace_insensitively(self) -> None:
        pkg = PackageLicense(
            name="gpu",
            version="1.0",
            license_expression=UNKNOWN_LICENSE,
            declared_license="  Proprietary\tLicense",
            category=LicenseCategory.UNKNOWN,
        )
        LicenseAuditor._apply_classifications(
            [pkg], {"Proprietary License": "permissive"}
        )
        assert pkg.category == LicenseCategory.PERMISSIVE

    def test_recognized_license_is_reclassified_by_its_spdx_id(self) -> None:
        pkg = PackageLicense(
            name="x",
            version="1.0",
            license_expression="MPL-2.0",
            category=LicenseCategory.WEAK_COPYLEFT,
        )
        LicenseAuditor._apply_classifications([pkg], {"MPL-2.0": "permissive"})
        assert pkg.category == LicenseCategory.PERMISSIVE
        assert pkg.category_overridden is True
        assert pkg.license_expression == "MPL-2.0"

    def test_not_detected_package_is_not_blanket_reclassified(self) -> None:
        pkg = PackageLicense(
            name="mystery",
            version="1.0",
            license_expression=UNKNOWN_LICENSE,
            category=LicenseCategory.UNKNOWN,
        )
        LicenseAuditor._apply_classifications([pkg], {"UNKNOWN": "permissive"})
        assert pkg.category == LicenseCategory.UNKNOWN
        assert pkg.category_overridden is False

    def test_component_of_compound_expression_is_not_matched(self) -> None:
        # Matching is on the whole license string, not AND/OR components.
        pkg = PackageLicense(
            name="x",
            version="1.0",
            license_expression="GPL-2.0-only AND MIT",
            category=LicenseCategory.STRONG_COPYLEFT,
        )
        unmatched = LicenseAuditor._apply_classifications(
            [pkg], {"GPL-2.0-only": "permissive"}
        )
        assert pkg.category == LicenseCategory.STRONG_COPYLEFT
        assert pkg.category_overridden is False
        assert unmatched == ["GPL-2.0-only"]

    def test_returns_unmatched_keys(self) -> None:
        pkg = self._unrecognized()  # declares "Proprietary License"
        unmatched = LicenseAuditor._apply_classifications(
            [pkg], {"Proprietary License": "permissive", "Typo License": "permissive"}
        )
        assert unmatched == ["Typo License"]

    def test_no_unmatched_when_all_match(self) -> None:
        pkg = self._unrecognized()
        unmatched = LicenseAuditor._apply_classifications(
            [pkg], {"Proprietary License": "permissive"}
        )
        assert unmatched == []

    def test_classification_warnings_built_for_unmatched(self) -> None:
        items = LicenseAuditor._classification_warnings(["Typo License"])
        assert len(items) == 1
        assert items[0].severity == "warning"
        assert "Typo License" in items[0].message
        assert "matched no package" in items[0].message


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
