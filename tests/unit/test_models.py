"""Tests for core data models."""

from __future__ import annotations

from license_audit.core.models import (
    DependencyNode,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
)


def _node(name: str, *deps: DependencyNode) -> DependencyNode:
    return DependencyNode(
        package=PackageLicense(name=name, version="1.0"),
        dependencies=list(deps),
    )


class TestDisplayLicense:
    def test_recognized_license_uses_expression(self) -> None:
        pkg = PackageLicense(
            name="click",
            version="8.1.0",
            license_expression="BSD-3-Clause",
            license_source=LicenseSource.PEP639,
            category=LicenseCategory.PERMISSIVE,
        )
        assert pkg.display_license == "BSD-3-Clause"

    def test_declared_string_preferred_when_present(self) -> None:
        pkg = PackageLicense(
            name="proprietary-package",
            version="12.0.0",
            license_expression="UNKNOWN",
            declared_license="Proprietary License",
            license_source=LicenseSource.METADATA,
            category=LicenseCategory.UNKNOWN,
        )
        assert pkg.display_license == "Proprietary License"

    def test_undetected_license_falls_back_to_unknown(self) -> None:
        pkg = PackageLicense(name="mystery", version="1.0.0")
        assert pkg.declared_license is None
        assert pkg.display_license == "UNKNOWN"


class TestDependencyNodeFlatten:
    def test_direct_deps_are_their_own_parent(self) -> None:
        tree = _node("root", _node("a"), _node("b"))
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["a"] == "a"
        assert parents["b"] == "b"

    def test_transitive_dep_attributed_to_top_level_parent(self) -> None:
        tree = _node("root", _node("a", _node("leaf")))
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["leaf"] == "a"

    def test_deep_chain_keeps_top_level_attribution(self) -> None:
        tree = _node("root", _node("a", _node("mid", _node("leaf"))))
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["mid"] == "a"
        assert parents["leaf"] == "a"

    def test_shared_transitive_dep_appears_once(self) -> None:
        shared_under_a = _node("shared")
        shared_under_b = _node("shared")
        tree = _node("root", _node("a", shared_under_a), _node("b", shared_under_b))
        packages = tree.flatten()
        assert [p.name for p in packages].count("shared") == 1
        parents = {p.name: p.parent for p in packages}
        assert parents["shared"] == "a"

    def test_direct_dep_also_required_transitively_stays_direct(self) -> None:
        tree = _node("root", _node("a", _node("b")), _node("b"))
        parents = {p.name: p.parent for p in tree.flatten()}
        assert parents["b"] == "b"

    def test_root_included_without_parent(self) -> None:
        tree = _node("root", _node("a"))
        root_pkg = next(p for p in tree.flatten() if p.name == "root")
        assert root_pkg.parent == ""
