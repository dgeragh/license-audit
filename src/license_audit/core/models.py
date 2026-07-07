"""Core data models for license_audit."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# Sentinel value used when a package's license cannot be detected.
UNKNOWN_LICENSE = "UNKNOWN"


class LicenseCategory(StrEnum):
    """Classification of a license by its copyleft/permissive nature."""

    PERMISSIVE = "permissive"
    WEAK_COPYLEFT = "weak-copyleft"
    STRONG_COPYLEFT = "strong-copyleft"
    NETWORK_COPYLEFT = "network-copyleft"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


# Permissiveness ranking: lower = more permissive
CATEGORY_RANK: dict[LicenseCategory, int] = {
    LicenseCategory.PERMISSIVE: 0,
    LicenseCategory.WEAK_COPYLEFT: 1,
    LicenseCategory.STRONG_COPYLEFT: 2,
    LicenseCategory.NETWORK_COPYLEFT: 3,
    LicenseCategory.PROPRIETARY: 4,
    LicenseCategory.UNKNOWN: 5,
}


class PolicyLevel(StrEnum):
    """License policy level, the maximum copyleft category allowed."""

    PERMISSIVE = "permissive"
    WEAK_COPYLEFT = "weak-copyleft"
    STRONG_COPYLEFT = "strong-copyleft"
    NETWORK_COPYLEFT = "network-copyleft"


class LicenseSource(StrEnum):
    """How the license was detected."""

    PEP639 = "pep639"
    METADATA = "metadata"
    CLASSIFIER = "classifier"
    OVERRIDE = "override"
    UNKNOWN = "unknown"


class Verdict(StrEnum):
    """Compatibility verdict between two licenses."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"
    CHECK_DEPENDENCY = "check-dependency"
    SAME = "same"


class PackageLicense(BaseModel):
    """License information for a single package."""

    name: str
    version: str
    license_expression: str = UNKNOWN_LICENSE
    declared_license: str | None = None
    license_source: LicenseSource = LicenseSource.UNKNOWN
    category: LicenseCategory = LicenseCategory.UNKNOWN
    category_overridden: bool = False
    parent: str = ""
    license_text: str | None = None
    ignored: bool = False
    ignore_reason: str = ""

    @property
    def display_license(self) -> str:
        """License string to show users.

        Prefers the raw declared identifier when the license could not be
        mapped to SPDX, so reports surface the actual string (e.g. "
        Proprietary License") instead of a bare ``UNKNOWN``.
        """
        return self.declared_license or self.license_expression


class DependencyNode(BaseModel):
    """A node in the dependency tree."""

    package: PackageLicense
    dependencies: list[DependencyNode] = Field(default_factory=list)

    def flatten(self) -> list[PackageLicense]:
        """Return all packages in the tree as a flat list (deduped by name).

        Each package's ``parent`` field is set to the top-level dependency
        that pulls it in (direct deps have parent set to the root project).
        """
        seen: set[str] = set()
        result: list[PackageLicense] = []
        # The root node itself
        if self.package.name not in seen:
            seen.add(self.package.name)
            result.append(self.package)
        # Attribute every direct dependency first, so one that another
        # direct dependency also requires still reads as direct.
        for dep in self.dependencies:
            if dep.package.name not in seen:
                seen.add(dep.package.name)
                dep.package.parent = dep.package.name
                result.append(dep.package)
        # Each direct dependency becomes the "top-level parent" for all
        # of its transitive deps
        for dep in self.dependencies:
            dep._flatten_inner(seen, result, dep.package.name)
        return result

    def _flatten_inner(
        self, seen: set[str], result: list[PackageLicense], top_level: str
    ) -> None:
        if self.package.name not in seen:
            seen.add(self.package.name)
            self.package.parent = top_level
            result.append(self.package)
        for dep in self.dependencies:
            dep._flatten_inner(seen, result, top_level)


class CompatibilityResult(BaseModel):
    """Result of checking compatibility between two licenses."""

    inbound: str
    outbound: str
    verdict: Verdict


class ActionItem(BaseModel):
    """An action the user should take."""

    severity: str = "warning"
    package: str = ""
    message: str


class LicensePolicy(BaseModel):
    """User-defined license policy."""

    policy_type: PolicyLevel = PolicyLevel.PERMISSIVE
    allowed_licenses: list[str] = Field(default_factory=list)
    denied_licenses: list[str] = Field(default_factory=list)
    fail_on_unknown: bool = True


class AnalysisReport(BaseModel):
    """Complete analysis output."""

    project_name: str = ""
    source: str = ""
    packages: list[PackageLicense] = Field(default_factory=list)
    incompatible_pairs: list[CompatibilityResult] = Field(default_factory=list)
    recommended_licenses: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    policy_passed: bool | None = None
