"""End-to-end ``LicenseAuditor`` tests against a real installed layout.

These run the unmocked auditor against a fake virtualenv built under
``tmp_path`` (see ``conftest.make_venv``). They verify the read to detect to
classify to policy to report flow, plus that config (overrides, ignored,
allow/deny, policy level) reaches the produced ``AnalysisReport``.
"""

from __future__ import annotations

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
        gpus = [p for p in report.packages if p.name.startswith("gpu_")]
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
        sdk = next(p for p in report.packages if p.name == "vendor_sdk")
        assert sdk.category == LicenseCategory.STRONG_COPYLEFT
        assert report.policy_passed is False
        assert report.incompatible_pairs == []
        assert report.recommended_licenses == []
        violations = [i for i in report.action_items if i.package == "vendor_sdk"]
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
        mpl = next(p for p in report.packages if p.name == "weak_pkg")
        assert mpl.category == LicenseCategory.PERMISSIVE
        assert mpl.category_overridden is True
        assert all(
            "MPL-2.0" not in (pair.inbound, pair.outbound)
            for pair in report.incompatible_pairs
        )
        assert report.policy_passed is True
        assert report.recommended_licenses

    def test_classification_matching_nothing_warns(
        self,
        tmp_path: Path,
        make_venv: VenvBuilder,
    ) -> None:
        """A classification keyed on a component of a compound expression
        matches nothing (matching is whole-string) and surfaces a warning."""
        _write_pyproject(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\nversion = "0.0.1"\n'
            "[tool.license-audit.license-classifications]\n"
            '"MPL-2.0" = "permissive"\n',
        )
        # The MPL only appears inside a compound, never standalone.
        make_venv(tmp_path / ".venv", {"compound_pkg": "MPL-2.0 AND MIT"})
        report = LicenseAuditor().run(target=tmp_path)
        compound = next(p for p in report.packages if p.name == "compound_pkg")
        # Compound keeps its computed category; the component is not reclassified.
        assert compound.category == LicenseCategory.WEAK_COPYLEFT
        assert compound.category_overridden is False
        warnings = [
            i.message
            for i in report.action_items
            if i.severity == "warning" and "matched no package" in i.message
        ]
        assert any("MPL-2.0" in m for m in warnings)

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
        sdk = next(p for p in report.packages if p.name == "vendor_sdk")
        assert sdk.category == LicenseCategory.PERMISSIVE
        assert sdk.category_overridden is True
        assert sdk.ignored is True
        # Ignored -> exempt from action items.
        assert not any(i.package == "vendor_sdk" for i in report.action_items)

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
