"""Tests for environment analysis."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

import pytest
from packaging.version import InvalidVersion

from license_audit.environment.analyze import _marker_matches, analyze_environment
from license_audit.util import MetadataReader


def _site_packages_or_skip() -> Path:
    """Resolve license_audit's own .venv site-packages, or skip."""
    venv_path = Path(__file__).parents[3] / ".venv"
    if not venv_path.exists():
        pytest.skip(".venv not found")
    lib_dir = venv_path / "lib"
    if lib_dir.is_dir():
        for child in lib_dir.iterdir():
            sp = child / "site-packages"
            if sp.is_dir():
                return sp
    win_sp = venv_path / "Lib" / "site-packages"
    if win_sp.is_dir():
        return win_sp
    pytest.skip("site-packages not found")


def _make_dist_info(
    site_packages: Path,
    name: str,
    version: str,
    license_expression: str | None = None,
    requires: list[str] | None = None,
) -> Path:
    dist_info = site_packages / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    body = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}"]
    if license_expression:
        body.append(f"License-Expression: {license_expression}")
    if requires:
        body.extend(f"Requires-Dist: {req}" for req in requires)
    (dist_info / "METADATA").write_text("\n".join(body) + "\n")
    return dist_info


class TestAnalyzeEnvironmentRealVenv:
    def test_own_venv(self) -> None:
        sp = _site_packages_or_skip()
        reader = MetadataReader.from_site_packages(sp)
        tree = analyze_environment("license_audit", reader)
        packages = tree.flatten()
        assert len(packages) > 0
        names = {p.name for p in packages}
        assert "click" in names

    def test_detects_licenses(self) -> None:
        sp = _site_packages_or_skip()
        reader = MetadataReader.from_site_packages(sp)
        tree = analyze_environment("license_audit", reader)
        click_pkgs = [p for p in tree.flatten() if p.name == "click"]
        assert len(click_pkgs) == 1
        assert click_pkgs[0].license_expression != "UNKNOWN"

    def test_overrides_applied(self) -> None:
        sp = _site_packages_or_skip()
        reader = MetadataReader.from_site_packages(sp)
        tree = analyze_environment(
            "license_audit", reader, overrides={"click": "Apache-2.0"}
        )
        click_pkgs = [p for p in tree.flatten() if p.name == "click"]
        assert click_pkgs[0].license_expression == "Apache-2.0"


class TestAnalyzeEnvironmentFakeSitePackages:
    """Tests against a fake site-packages built in tmp_path."""

    def test_walks_requires_dist_recursively(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=["leaf>=1.0"],
        )
        _make_dist_info(tmp_path, "leaf", "1.0", license_expression="Apache-2.0")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("rootpkg", reader)
        names = {p.name for p in tree.flatten()}
        assert "rootpkg" in names
        assert "leaf" in names

    def test_walks_arbitrarily_deep_transitive_chain(self, tmp_path: Path) -> None:
        """A 5-level chain (root -> a -> b -> c -> d -> e) must surface every level.

        Pins the contract that `_resolve_package` recurses without depth limit;
        only cycles are broken via the visited set.
        """
        chain = ["root", "a", "b", "c", "d", "e"]
        for current, nxt in pairwise(chain):
            _make_dist_info(
                tmp_path,
                current,
                "1.0",
                license_expression="MIT",
                requires=[f"{nxt}>=1.0"],
            )
        _make_dist_info(tmp_path, chain[-1], "1.0", license_expression="MIT")

        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("root", reader)
        names = {p.name for p in tree.flatten()}
        assert names >= set(chain)

    def test_dependency_cycle_does_not_recurse_forever(self, tmp_path: Path) -> None:
        """If A depends on B and B depends back on A, we still terminate."""
        _make_dist_info(
            tmp_path, "a", "1.0", license_expression="MIT", requires=["b>=1.0"]
        )
        _make_dist_info(
            tmp_path, "b", "1.0", license_expression="MIT", requires=["a>=1.0"]
        )
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("a", reader)
        names = {p.name for p in tree.flatten()}
        assert names >= {"a", "b"}

    def test_orphan_packages_appended(self, tmp_path: Path) -> None:
        """Packages unreachable from the root still appear in the tree."""
        _make_dist_info(tmp_path, "rootpkg", "1.0", license_expression="MIT")
        _make_dist_info(tmp_path, "orphan", "2.0", license_expression="BSD-3-Clause")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("rootpkg", reader)
        assert "orphan" in {p.name for p in tree.flatten()}

    def test_root_absent_lists_all_installed(self, tmp_path: Path) -> None:
        """When the root project isn't installed, every package still surfaces."""
        _make_dist_info(tmp_path, "leaf_a", "1.0", license_expression="MIT")
        _make_dist_info(tmp_path, "leaf_b", "1.0", license_expression="Apache-2.0")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("synth_root", reader)
        names = {p.name for p in tree.flatten()}
        assert names == {"synth-root", "leaf-a", "leaf-b"}

    def test_direct_dep_required_transitively_stays_direct(
        self, tmp_path: Path
    ) -> None:
        """A direct dependency that another direct dependency also requires
        is still attributed as direct."""
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=["liba>=1.0", "libb>=1.0"],
        )
        _make_dist_info(
            tmp_path, "liba", "1.0", license_expression="MIT", requires=["libb>=1.0"]
        )
        _make_dist_info(tmp_path, "libb", "1.0", license_expression="MIT")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("rootpkg", reader)
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["libb"] == "libb"

    def test_extra_gated_dep_included_when_extra_requested(
        self, tmp_path: Path
    ) -> None:
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=["withextras[fast]>=1.0"],
        )
        _make_dist_info(
            tmp_path,
            "withextras",
            "1.0",
            license_expression="MIT",
            requires=['speedup>=1.0; extra == "fast"'],
        )
        _make_dist_info(tmp_path, "speedup", "1.0", license_expression="MIT")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("rootpkg", reader)
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["speedup"] == "withextras"

    def test_extra_gated_dep_rescued_as_direct_without_extra(
        self, tmp_path: Path
    ) -> None:
        """A dep gated behind an unrequested extra isn't walked as a child,
        but the leftover-append still audits it, attributed as direct. Known
        limitation: the parent is lost, not the package."""
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=["withextras>=1.0"],
        )
        _make_dist_info(
            tmp_path,
            "withextras",
            "1.0",
            license_expression="MIT",
            requires=['speedup>=1.0; extra == "fast"'],
        )
        _make_dist_info(tmp_path, "speedup", "1.0", license_expression="MIT")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("rootpkg", reader)
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["speedup"] == "speedup"

    def test_false_marker_dep_rescued_as_direct(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=['legacy>=1.0; python_version < "3.0"'],
        )
        _make_dist_info(tmp_path, "legacy", "1.0", license_expression="MIT")
        reader = MetadataReader.from_site_packages(tmp_path)
        tree = analyze_environment("rootpkg", reader)
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["legacy"] == "legacy"

    def test_declared_but_uninstalled_dep_is_skipped(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=["installed_dep>=1.0", "ghost>=1.0"],
        )
        _make_dist_info(
            tmp_path, "installed_dep", "1.0", license_expression="Apache-2.0"
        )
        reader = MetadataReader.from_site_packages(tmp_path)
        names = {p.name for p in analyze_environment("rootpkg", reader).flatten()}
        assert "installed-dep" in names
        assert "ghost" not in names

    def test_unevaluable_marker_dep_rescued_as_direct(self, tmp_path: Path) -> None:
        # packaging < 26 raises on platform_release markers against a Linux
        # kernel string; the dep must still land in the tree, not crash the walk.
        _make_dist_info(
            tmp_path,
            "rootpkg",
            "1.0",
            license_expression="MIT",
            requires=['kernelonly>=1.0; platform_release >= "5"'],
        )
        _make_dist_info(tmp_path, "kernelonly", "1.0", license_expression="MIT")
        reader = MetadataReader.from_site_packages(tmp_path)
        with patch(
            "packaging.markers.Marker.evaluate",
            side_effect=InvalidVersion("Invalid version: '6.5.0-14-generic'"),
        ):
            tree = analyze_environment("rootpkg", reader)
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["kernelonly"] == "kernelonly"


class TestMarkerMatches:
    def test_unevaluable_marker_is_false_for_every_extra(self) -> None:
        class _Marker:
            def evaluate(self, environment: dict[str, str]) -> bool:
                raise InvalidVersion(environment["extra"] or "bare")

        assert _marker_matches(_Marker(), frozenset({"fast"})) is False
