"""Policy evaluation and action-item generation."""

from __future__ import annotations

from license_audit.config import LicenseAuditConfig
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import (
    CATEGORY_RANK,
    UNKNOWN_LICENSE,
    ActionItem,
    CompatibilityResult,
    LicenseCategory,
    LicensePolicy,
    PackageLicense,
    PolicyLevel,
)
from license_audit.licenses.spdx import SpdxNormalizer


class PolicyEngine:
    """Build and evaluate license policies, generating human-readable action items."""

    POLICY_MAX_RANK: dict[PolicyLevel, int] = {
        PolicyLevel.PERMISSIVE: CATEGORY_RANK[LicenseCategory.PERMISSIVE],
        PolicyLevel.WEAK_COPYLEFT: CATEGORY_RANK[LicenseCategory.WEAK_COPYLEFT],
        PolicyLevel.STRONG_COPYLEFT: CATEGORY_RANK[LicenseCategory.STRONG_COPYLEFT],
        PolicyLevel.NETWORK_COPYLEFT: CATEGORY_RANK[LicenseCategory.NETWORK_COPYLEFT],
    }

    def __init__(
        self,
        classifier: LicenseClassifier | None = None,
        normalizer: SpdxNormalizer | None = None,
    ) -> None:
        self._classifier = classifier or LicenseClassifier()
        self._normalizer = normalizer or SpdxNormalizer()

    def max_rank(self, level: PolicyLevel) -> int | None:
        """Return the maximum category rank ``level`` permits."""
        return self.POLICY_MAX_RANK.get(level)

    def exceeds_rank(self, pkg: PackageLicense, max_rank: int | None) -> bool:
        """Return True if ``pkg`` exceeds ``max_rank``. UNKNOWN categories never exceed."""
        if max_rank is None or pkg.category == LicenseCategory.UNKNOWN:
            return False
        return CATEGORY_RANK.get(pkg.category, 5) > max_rank

    def build_policy(self, config: LicenseAuditConfig) -> LicensePolicy:
        """Promote a ``LicenseAuditConfig`` into a pre-validated ``LicensePolicy``."""
        return LicensePolicy(
            policy_type=config.policy,
            allowed_licenses=config.allowed_licenses,
            denied_licenses=config.denied_licenses,
            fail_on_unknown=config.fail_on_unknown,
        )

    def check(
        self,
        packages: list[PackageLicense],
        policy: LicensePolicy,
    ) -> bool:
        """Return True if every package satisfies ``policy``."""
        max_rank = self.max_rank(policy.policy_type)

        denied_set = (
            {d.lower() for d in policy.denied_licenses}
            if policy.denied_licenses
            else set()
        )
        allowed_set = (
            {a.lower() for a in policy.allowed_licenses}
            if policy.allowed_licenses
            else set()
        )

        for pkg in packages:
            if policy.fail_on_unknown and self.is_unknown(pkg):
                return False

            if self.exceeds_rank(pkg, max_rank):
                return False

            if denied_set:
                for lic in self._normalizer.get_simple_licenses(pkg.license_expression):
                    if lic.lower() in denied_set:
                        return False

            if allowed_set:
                for lic in self._normalizer.get_simple_licenses(pkg.license_expression):
                    if (
                        lic.lower() not in allowed_set
                        and pkg.license_expression != UNKNOWN_LICENSE
                    ):
                        return False

        return True

    def build_action_items(
        self,
        packages: list[PackageLicense],
        incompatible: list[CompatibilityResult],
        config: LicenseAuditConfig,
    ) -> list[ActionItem]:
        """Generate action items for unknown licenses, incompatible pairs,
        denied licenses, and copyleft policy violations.
        """
        items: list[ActionItem] = []

        for pkg in packages:
            if self.is_unknown(pkg):
                items.append(
                    ActionItem(
                        severity="warning",
                        package=pkg.name,
                        message=self.unknown_message(pkg),
                    ),
                )

        for pair in incompatible:
            items.append(
                ActionItem(
                    severity="error",
                    package="",
                    message=(
                        f"Licenses '{pair.inbound}' and '{pair.outbound}' are mutually "
                        f"incompatible. Dependencies using these licenses cannot coexist."
                    ),
                ),
            )

        if config.denied_licenses:
            items.extend(self.denied_license_items(packages, config.denied_licenses))

        max_rank = self.max_rank(config.policy)
        for pkg in packages:
            if self.exceeds_rank(pkg, max_rank):
                items.append(
                    ActionItem(
                        severity="error",
                        package=pkg.name,
                        message=(
                            f"Package '{pkg.name}' uses {pkg.category.value} license "
                            f"'{pkg.license_expression}', which violates the "
                            f"'{config.policy}' policy."
                        ),
                    ),
                )
            elif pkg.category in (
                LicenseCategory.STRONG_COPYLEFT,
                LicenseCategory.NETWORK_COPYLEFT,
            ):
                items.append(
                    ActionItem(
                        severity="warning",
                        package=pkg.name,
                        message=(
                            f"Package '{pkg.name}' uses {pkg.category.value} license "
                            f"'{pkg.license_expression}'. This may require your project "
                            f"to use a compatible copyleft license."
                        ),
                    ),
                )

        return items

    def denied_license_items(
        self,
        packages: list[PackageLicense],
        denied_licenses: list[str],
    ) -> list[ActionItem]:
        """Build action items for packages using denied licenses."""
        items: list[ActionItem] = []
        denied_set = {d.lower() for d in denied_licenses}
        for pkg in packages:
            for lic in self._normalizer.get_simple_licenses(pkg.license_expression):
                if lic.lower() in denied_set:
                    items.append(
                        ActionItem(
                            severity="error",
                            package=pkg.name,
                            message=(
                                f"Package '{pkg.name}' uses denied license '{lic}'. "
                                f"Find an alternative or request an exemption."
                            ),
                        ),
                    )
        return items

    @staticmethod
    def is_unknown(pkg: PackageLicense) -> bool:
        """Return True if ``pkg`` has an unknown or unrecognized license."""
        return (
            pkg.license_expression == UNKNOWN_LICENSE
            or pkg.category == LicenseCategory.UNKNOWN
        )

    @staticmethod
    def unknown_message(pkg: PackageLicense) -> str:
        """Human-readable message explaining why ``pkg``'s license is unknown."""
        if pkg.license_expression == UNKNOWN_LICENSE:
            detail = f"License for '{pkg.name}' could not be detected."
        else:
            detail = (
                f"License '{pkg.license_expression}' for '{pkg.name}' "
                f"is not a recognized SPDX expression."
            )
        return (
            f"{detail} Add an override in [tool.license-audit.overrides] "
            f"or check manually."
        )
