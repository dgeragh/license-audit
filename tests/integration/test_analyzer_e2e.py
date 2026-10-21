"""End-to-end ``LicenseAuditor`` tests against a real installed layout.

These run the unmocked auditor against a fake virtualenv built under
``tmp_path`` (see ``conftest.make_venv``). They verify the read to detect to
classify to policy to report flow, plus that config (overrides, ignored,
allow/deny, policy level) reaches the produced ``AnalysisReport``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from license_audit.core.analyzer import LicenseAuditor
from license_audit.core.models import LicenseCategory

VenvBuilder = Callable[[Path, dict[str, str]], Path]


def _write_pyproject(path: Path, body: str) -> None:
    path.write_text(body)


class TestVenvAnalysis:
    def test_reads_installed_packages(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        venv = make_venv(
            tmp_path / ".venv",
            {"click": "BSD-3-Clause", "rich": "MIT"},
        )
        report = LicenseAuditor().run(target=venv)
        names = {p.name for p in report.packages}
        assert {"click", "rich"}.issubset(names)

    def test_project_dir_resolves_to_venv(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        assert "click" in {p.name for p in report.packages}


class TestConfigPropagation:
    def test_override_applied_to_package(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.overrides]\n"
            'click = "Apache-2.0"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        click = next(p for p in report.packages if p.name == "click")
        assert click.license_expression == "Apache-2.0"

    def test_unrecognized_license_preserves_declared_string(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A declared-but-unrecognized license surfaces its raw string and
        still counts as unknown (so fail-on-unknown CI gating keeps working)."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(tmp_path / ".venv", {"gpu": "Proprietary License"})
        report = LicenseAuditor().run(target=tmp_path)
        gpu = next(p for p in report.packages if p.name == "gpu")
        assert gpu.license_expression == "UNKNOWN"
        assert gpu.declared_license == "Proprietary License"
        assert gpu.display_license == "Proprietary License"
        assert gpu.category == LicenseCategory.UNKNOWN

    def test_license_classification_whitelist_resolves_unknown(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming a declared license a category covers every package that
        declares it: it is reclassified, no longer unknown, and policy passes."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"Proprietary License" = "permissive"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"gpu_a": "Proprietary License", "gpu_b": "Proprietary License"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        gpus = [p for p in report.packages if p.name.startswith("gpu-")]
        assert len(gpus) == 2
        for gpu in gpus:
            assert gpu.category == LicenseCategory.PERMISSIVE
            assert gpu.category_overridden is True
            assert gpu.declared_license == "Proprietary License"
        assert report.policy_passed is True
        # No longer blocked from recommending an outbound license.
        assert report.recommended_licenses

    def test_deemed_strong_copyleft_fails_policy_but_stays_out_of_compatibility(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming a license strong-copyleft makes a permissive policy reject
        it (with a violation action item), while it stays out of pairwise
        compatibility (no SPDX id) and suppresses recommendations."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"Vendor EULA" = "strong-copyleft"\n',
        )
        make_venv(tmp_path / ".venv", {"vendor_sdk": "Vendor EULA"})
        report = LicenseAuditor().run(target=tmp_path)
        sdk = next(p for p in report.packages if p.name == "vendor-sdk")
        assert sdk.category == LicenseCategory.STRONG_COPYLEFT
        assert report.policy_passed is False
        assert report.incompatible_pairs == []
        assert report.recommended_licenses == []
        violations = [i for i in report.action_items if i.package == "vendor-sdk"]
        assert violations
        assert any("Vendor EULA" in i.message for i in violations)

    def test_reclassifying_recognized_license_waives_its_compatibility(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming a recognized SPDX license (MPL-2.0) permissive applies by
        its id, drops it from pairwise compatibility (so its conflicts are
        waived), and lets recommendations proceed."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"MPL-2.0" = "permissive"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"weak_pkg": "MPL-2.0", "py_pkg": "PSF-2.0", "mit_pkg": "MIT"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        mpl = next(p for p in report.packages if p.name == "weak-pkg")
        assert mpl.category == LicenseCategory.PERMISSIVE
        assert mpl.category_overridden is True
        assert all(
            "MPL-2.0" not in (pair.license_a, pair.license_b)
            for pair in report.incompatible_pairs
        )
        assert report.policy_passed is True
        assert report.recommended_licenses

    def test_compound_expression_recommendations_match_compatibility(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """An OR nested inside an AND resolves the same way for the
        recommendation and the compatibility check: the report must not
        recommend a license its own incompatibility scan would flag."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"mixed": "MIT AND (GPL-3.0-only OR Apache-2.0)"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.incompatible_pairs == []
        assert report.recommended_licenses[0] == "MIT"

    def test_dual_license_order_does_not_create_conflicts(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A dependency declared Apache-first (packaging, cryptography) next
        to GPL-2.0-only is satisfiable through its BSD branch."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"dual": "Apache-2.0 OR BSD-2-Clause", "gpl": "GPL-2.0-only"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.incompatible_pairs == []
        assert "GPL-2.0-only" in report.recommended_licenses

    def test_weak_copyleft_tree_has_no_conflicts(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """certifi (MPL-2.0) beside typing-extensions (PSF-2.0), as requests and
        pydantic install them: weak copyleft stays with its own files, so a
        permissive outbound license fits and nothing conflicts."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            '[tool.license-audit]\npolicy = "weak-copyleft"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {
                "certifi": "MPL-2.0",
                "typing-extensions": "PSF-2.0",
                "requests": "Apache-2.0",
                "pydantic": "MIT",
            },
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.incompatible_pairs == []
        assert report.recommended_licenses[0] == "MIT"
        assert report.policy_passed is True

    def test_incompatible_pair_fails_policy_passed(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """policy_passed is the verdict `check` reaches: a conflict fails it
        even when every package fits the policy level."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            '[tool.license-audit]\npolicy = "strong-copyleft"\n',
        )
        make_venv(tmp_path / ".venv", {"gpl2": "GPL-2.0-only", "apache": "Apache-2.0"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.incompatible_pairs
        assert report.policy_passed is False

    def test_review_only_fit_passes_and_says_so(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """GPL-2.0-only beside LGPL-2.1-only fits GPL-2.0-only only through
        OSADL's "Check dependency" verdict: the check passes, and instead of
        reporting conflicting requirements the report lists it for review."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            '[tool.license-audit]\npolicy = "strong-copyleft"\n',
        )
        make_venv(tmp_path / ".venv", {"gpl": "GPL-2.0-only", "lgpl": "LGPL-2.1-only"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is True
        assert report.incompatible_pairs == []
        assert report.incompatible_groups == []
        assert report.recommended_licenses == []
        assert report.review_licenses == ["GPL-2.0-only"]
        assert any(
            item.severity == "warning" and "definite fit" in item.message
            for item in report.action_items
        )

    def test_conflict_no_pair_explains_fails_policy_passed(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """EUPL-1.1, Apache-2.0, and PSF-2.0 pair up fine, but no outbound
        license satisfies all three, so the check fails on the group."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            '[tool.license-audit]\npolicy = "strong-copyleft"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"eupl": "EUPL-1.1", "requests": "Apache-2.0", "typing-ext": "PSF-2.0"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.incompatible_pairs == []
        assert [g.licenses for g in report.incompatible_groups] == [
            ["EUPL-1.1", "Apache-2.0", "PSF-2.0"],
        ]
        assert report.recommended_licenses == []
        assert report.review_licenses == []
        assert report.policy_passed is False
        assert any(
            item.severity == "error" and "incompatible together" in item.message
            for item in report.action_items
        )

    def test_less_permissive_dual_license_branch_avoids_conflict(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A dependency dual-licensed Apache-2.0 OR GPL-2.0-only fits a
        GPL-2.0-only tree through its GPL branch, though Apache-2.0 alone
        would conflict."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"dual": "Apache-2.0 OR GPL-2.0-only", "gpl": "GPL-2.0-only"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert report.incompatible_pairs == []
        assert "GPL-2.0-only" in report.recommended_licenses

    def test_classified_component_keeps_sibling_in_recommendations(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming CNRI-Python permissive waives only that component; the
        Apache-2.0 sibling still rules out the GPL-2.0-only outbound the
        incompatibility scan flags."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"CNRI-Python" = "permissive"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"legacy_pkg": "Apache-2.0 AND CNRI-Python", "gpl_pkg": "GPL-2.0-only"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert any(
            {p.license_a, p.license_b} == {"Apache-2.0", "GPL-2.0-only"}
            for p in report.incompatible_pairs
        )
        assert report.recommended_licenses == []

    def test_classification_matching_nothing_warns(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A classification key that matches neither a whole license nor any
        component (a typo) surfaces a warning."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"Typo License" = "permissive"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        warnings = [
            i.message
            for i in report.action_items
            if i.severity == "warning" and "matched no package" in i.message
        ]
        assert any("Typo License" in m for m in warnings)

    def test_component_classification_reclassifies_compound(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming a component permissive re-evaluates the whole AND, and the
        component's id is dropped from compatibility."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"MPL-2.0" = "permissive"\n',
        )
        make_venv(tmp_path / ".venv", {"compound_pkg": "MPL-2.0 AND MIT"})
        report = LicenseAuditor().run(target=tmp_path)
        compound = next(p for p in report.packages if p.name == "compound-pkg")
        assert compound.category == LicenseCategory.PERMISSIVE
        assert compound.category_overridden is True
        # MPL waived even though it was only a component.
        assert all(
            "MPL-2.0" not in (p.license_a, p.license_b)
            for p in report.incompatible_pairs
        )
        # No spurious no-match warning (the component matched).
        assert not any("matched no package" in i.message for i in report.action_items)

    def test_component_classification_with_unclassified_spdx_id(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming a valid SPDX component that has no classification data
        (CNRI-Python) resolves a compound expression instead of being
        dismissed as a typo."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"CNRI-Python" = "permissive"\n',
        )
        make_venv(tmp_path / ".venv", {"legacy_pkg": "Apache-2.0 AND CNRI-Python"})
        report = LicenseAuditor().run(target=tmp_path)
        pkg = next(p for p in report.packages if p.name == "legacy-pkg")
        assert pkg.license_expression == "Apache-2.0 AND CNRI-Python"
        assert pkg.category == LicenseCategory.PERMISSIVE
        assert pkg.category_overridden is True
        assert report.policy_passed is True
        assert not any("matched no package" in i.message for i in report.action_items)
        assert all(
            "CNRI-Python" not in (p.license_a, p.license_b)
            for p in report.incompatible_pairs
        )

    def test_unclassified_spdx_component_stays_unknown(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Without a classification, a valid SPDX component that has no
        classification data leaves the package unknown and is named in the
        action item."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(tmp_path / ".venv", {"legacy_pkg": "Apache-2.0 AND CC-BY-SA-4.0"})
        report = LicenseAuditor().run(target=tmp_path)
        pkg = next(p for p in report.packages if p.name == "legacy-pkg")
        assert pkg.license_expression == "Apache-2.0 AND CC-BY-SA-4.0"
        assert pkg.category == LicenseCategory.UNKNOWN
        assert report.policy_passed is False
        assert any("'CC-BY-SA-4.0'" in i.message for i in report.action_items)

    def test_supplemental_classification_resolves_common_license(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """numpy's CC0-1.0 component and regex's CNRI-Python aren't in the
        OSADL data but are classified built-in, so neither reads unknown."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {
                "numpy": "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
                "regex": "Apache-2.0 AND CNRI-Python",
            },
        )
        report = LicenseAuditor().run(target=tmp_path)
        assert {p.category for p in report.packages} == {LicenseCategory.PERMISSIVE}
        assert not any(p.category_overridden for p in report.packages)
        assert report.recommended_licenses[0] == "MIT"
        assert report.policy_passed is True

    def test_unmappable_classifier_beside_mapped_ones_warns(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """docutils lists Public Domain, BSD, and an unversioned GPL classifier;
        the GPL one can't be mapped, so the OR of the others carries a warning."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        venv = make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        dist_info = next(venv.glob("lib/*/site-packages")) / "docutils-0.21.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: docutils\nVersion: 0.21\n"
            "Classifier: License :: Public Domain\n"
            "Classifier: License :: OSI Approved :: BSD License\n"
            "Classifier: License :: OSI Approved :: GNU General Public License (GPL)\n"
        )
        report = LicenseAuditor().run(target=tmp_path)
        docutils = next(p for p in report.packages if p.name == "docutils")
        assert docutils.license_expression == "BSD-3-Clause OR Unlicense"
        warnings = [i for i in report.action_items if i.package == "docutils"]
        assert len(warnings) == 1
        assert "GNU General Public License (GPL)" in warnings[0].message

    def test_classifier_reading_narrower_than_license_field_warns(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """PyInstaller's GPLv2 classifier drops the or-later grant and the
        bootloader exception its License field states."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n',
        )
        venv = make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        site_packages = next(venv.glob("lib/*/site-packages"))
        dist_info = site_packages / "pyinstaller-6.22.3.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: pyinstaller\nVersion: 6.22.3\n"
            "License: GPLv2-or-later with a special exception which allows to "
            "use PyInstaller to build and distribute non-free programs\n"
            "Classifier: License :: OSI Approved :: GNU General Public License "
            "v2 (GPLv2)\n"
        )
        report = LicenseAuditor().run(target=tmp_path)
        pyinstaller = next(p for p in report.packages if p.name == "pyinstaller")
        assert pyinstaller.license_expression == "GPL-2.0-only"
        warnings = [i for i in report.action_items if i.package == "pyinstaller"]
        assert any(
            "also allows later versions and adds an exception" in w.message
            for w in warnings
        )

    def test_deemed_or_branch_keeps_conflicts_visible(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """Deeming one OR branch steers compatibility to the same branch as
        classification, so conflicts on the chosen branch still surface."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit]\n"
            'policy = "network-copyleft"\n'
            "[tool.license-audit.license-classifications]\n"
            '"MIT" = "proprietary"\n',
        )
        make_venv(
            tmp_path / ".venv",
            {"pkga": "GPL-3.0-only OR MIT", "pkgb": "GPL-2.0-only"},
        )
        report = LicenseAuditor().run(target=tmp_path)
        pkga = next(p for p in report.packages if p.name == "pkga")
        assert pkga.category == LicenseCategory.STRONG_COPYLEFT
        assert any(
            {pair.license_a, pair.license_b} == {"GPL-2.0-only", "GPL-3.0-only"}
            for pair in report.incompatible_pairs
        )

    def test_whole_expression_classification_waives_compatibility(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A classification keyed by the full expression drops its components
        from compatibility analysis, the same as a component key."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"GPL-2.0-only AND GPL-3.0-only" = "permissive"\n',
        )
        make_venv(tmp_path / ".venv", {"dualgpl": "GPL-2.0-only AND GPL-3.0-only"})
        report = LicenseAuditor().run(target=tmp_path)
        pkg = next(p for p in report.packages if p.name == "dualgpl")
        assert pkg.category == LicenseCategory.PERMISSIVE
        assert pkg.category_overridden is True
        assert report.incompatible_pairs == []
        assert report.policy_passed is True

    def test_classified_and_ignored_package(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A package can be both classified (by license string) and ignored
        (by name); it carries the deemed category and the ignore marker."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"Vendor EULA" = "permissive"\n'
            "[tool.license-audit.ignored-packages]\n"
            'vendor_sdk = "Reviewed and vendored"\n',
        )
        make_venv(tmp_path / ".venv", {"vendor_sdk": "Vendor EULA"})
        report = LicenseAuditor().run(target=tmp_path)
        sdk = next(p for p in report.packages if p.name == "vendor-sdk")
        assert sdk.category == LicenseCategory.PERMISSIVE
        assert sdk.category_overridden is True
        assert sdk.ignored is True
        # Ignored -> exempt from action items.
        assert not any(i.package == "vendor-sdk" for i in report.action_items)

    def test_ignored_package_marked_in_report(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.ignored-packages]\n"
            'click = "Smoke test exemption"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        click = next(p for p in report.packages if p.name == "click")
        assert click.ignored is True
        assert click.ignore_reason == "Smoke test exemption"

    def test_denied_license_fails_policy(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit]\n"
            'denied-licenses = ["BSD-3-Clause"]\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is False

    def test_allowed_licenses_pass_when_matching(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit]\n"
            'allowed-licenses = ["BSD-3-Clause"]\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is True

    def test_allowed_licenses_fail_when_not_matching(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit]\n"
            'allowed-licenses = ["MIT"]\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
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
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
        policy: str,
        expected_pass: bool,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit]\n"
            f'policy = "{policy}"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "MPL-2.0"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.policy_passed is expected_pass

    def test_config_flag_audits_external_venv(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A venv outside the project still gets the project's policy."""
        project = tmp_path / "project"
        project.mkdir()
        _write_pyproject(
            project / "pyproject.toml",
            '[project]\nname = "from-config"\nversion = "0.0.1"\n'
            "[tool.license-audit]\n"
            'denied-licenses = ["BSD-3-Clause"]\n',
        )
        venv = make_venv(tmp_path / "env", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=venv, config_dir=project)
        assert report.project_name == "from-config"
        assert report.policy_passed is False


class TestRequiredDependencies:
    """A dependency the project requires but the environment lacks fails the
    audit: it usually means the wrong environment was audited."""

    def test_missing_required_dependency_fails(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "app"\ndependencies = ["click", "html2text>=2024"]\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.missing_dependencies == ["html2text"]
        assert report.policy_passed is False
        assert report.recommended_licenses == []
        first = report.action_items[0]
        assert first.severity == "error"
        assert "weren't checked: html2text." in first.message

    def test_long_missing_list_is_bounded(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        deps = ", ".join(f'"dep{i:02}"' for i in range(12))
        _write_pyproject(
            tmp_path / "pyproject.toml",
            f'[project]\nname = "app"\ndependencies = [{deps}]\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        assert len(report.missing_dependencies) == 12
        assert "dep09, and 2 more." in report.action_items[0].message

    def test_extras_groups_and_ignored_packages_not_required(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "app"\ndependencies = ["click", "opencv-python"]\n'
            '[project.optional-dependencies]\nfast = ["orjson"]\n'
            '[dependency-groups]\ndev = ["pytest"]\n'
            "[tool.license-audit.ignored-packages]\n"
            'opencv-python = "Provided by opencv-python-headless"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause"})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.missing_dependencies == []
        assert report.policy_passed is True
        assert report.recommended_licenses


class TestProjectIdentity:
    """The project is never audited as a dependency of itself."""

    def test_poetry_project_name(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[tool.poetry]\nname = "Poetry_App"\nversion = "0.1.0"\n'
            '[tool.poetry.dependencies]\npython = "^3.11"\nclick = "*"\n',
        )
        make_venv(tmp_path / ".venv", {"click": "BSD-3-Clause", "poetry-app": ""})
        report = LicenseAuditor().run(target=tmp_path)
        assert report.project_name == "Poetry_App"
        assert {p.name for p in report.packages} == {"click"}
        assert report.policy_passed is True

    def test_installed_project_without_pyproject_name(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A setup.py project installed editable is found by direct_url.json."""
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        venv = make_venv(tmp_path / ".venv", {"legacy-app": "", "click": "MIT"})
        dist_info = next(venv.glob("lib/*/site-packages/legacy-app-*.dist-info"))
        direct_url = {"dir_info": {"editable": True}, "url": tmp_path.as_uri()}
        (dist_info / "direct_url.json").write_text(json.dumps(direct_url))
        report = LicenseAuditor().run(target=venv)
        assert report.project_name == "legacy-app"
        assert {p.name for p in report.packages} == {"click"}
