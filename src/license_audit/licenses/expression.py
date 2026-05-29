"""AND/OR-aware evaluation of SPDX license expressions."""

from __future__ import annotations

from typing import Any

from license_expression import AND, OR, LicenseSymbol

from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import CATEGORY_RANK, LicenseCategory
from license_audit.licenses.spdx import SpdxNormalizer


def normalize_license_key(value: str) -> str:
    """Canonical form for matching a license string against config keys.

    Collapses internal whitespace and lowercases, so a configured
    classification matches regardless of casing or irregular spacing in
    package metadata.
    """
    return " ".join(value.split()).lower()


# Maps a normalized license string to a user-deemed category, used to override
# a component's classification while evaluating an AND/OR expression.
CategoryOverrides = dict[str, LicenseCategory]


class ExpressionEvaluator:
    """Evaluates SPDX expressions with AND/OR semantics.

    `A AND B` requires complying with both, so the effective constraint
    is the most restrictive component. `A OR B` lets the consumer pick
    one, so the effective constraint is the most permissive alternative.
    """

    def __init__(
        self,
        classifier: LicenseClassifier | None = None,
        normalizer: SpdxNormalizer | None = None,
    ) -> None:
        self._classifier = classifier or LicenseClassifier()
        self._normalizer = normalizer or SpdxNormalizer()

    def alternatives(self, expr: str) -> list[list[str]]:
        """Distribute AND over OR into a list of jointly-required id sets.

        `A AND (B OR C)` becomes `[[A, B], [A, C]]`. Returns `[[]]` when
        the expression can't be parsed.
        """
        parsed = self._normalizer.parse_expression(expr)
        if parsed is None:
            return [[]]
        return self._walk_alternatives(parsed)

    def required_ids(self, expr: str) -> list[str]:
        """Ids the project must comply with after resolving every OR.

        Picks the alternative whose worst-case license has the lowest
        permissiveness rank.
        """
        non_empty = [alt for alt in self.alternatives(expr) if alt]
        if not non_empty:
            return []
        best = min(non_empty, key=self._alt_rank)
        return list(dict.fromkeys(best))

    def unknown_components(self, expr: str) -> list[str]:
        """Ids in the chosen alternative that classify as UNKNOWN."""
        non_empty = [alt for alt in self.alternatives(expr) if alt]
        if not non_empty:
            return []
        best = min(non_empty, key=self._alt_rank)
        return [
            lic
            for lic in dict.fromkeys(best)
            if self._classifier.classify(lic) == LicenseCategory.UNKNOWN
        ]

    def classify(
        self, expr: str, overrides: CategoryOverrides | None = None
    ) -> LicenseCategory:
        """Category of the best-case alternative for `expr`.

        `overrides` lets a caller force the category of individual component
        licenses (a user classification). An AND keeps the most restrictive
        component, so a deemed-restrictive component dominates; a deemed-
        permissive one stops binding. An OR keeps the most permissive
        alternative, so re-evaluation handles both correctly.
        """
        non_empty = [alt for alt in self.alternatives(expr) if alt]
        if not non_empty:
            return self._component_category(expr, overrides)
        best = min(non_empty, key=lambda alt: self._alt_rank(alt, overrides))
        return max(
            (self._component_category(lic, overrides) for lic in best),
            key=lambda c: CATEGORY_RANK.get(c, 5),
        )

    def passes_denied_allowed(
        self,
        expr: str,
        denied: set[str],
        allowed: set[str],
    ) -> bool:
        """True if at least one alternative avoids `denied` and fits `allowed`.

        `denied` and `allowed` must be lower-cased SPDX ids. An empty
        `allowed` set means no allowlist constraint.
        """
        for alt in self.alternatives(expr):
            if not alt:
                continue
            lowered = [lic.lower() for lic in alt]
            if any(lic in denied for lic in lowered):
                continue
            if allowed and any(lic not in allowed for lic in lowered):
                continue
            return True
        return False

    def _alt_rank(
        self, alt: list[str], overrides: CategoryOverrides | None = None
    ) -> int:
        return max(
            (
                CATEGORY_RANK.get(self._component_category(lic, overrides), 5)
                for lic in alt
            ),
            default=CATEGORY_RANK[LicenseCategory.UNKNOWN],
        )

    def _component_category(
        self, lic: str, overrides: CategoryOverrides | None = None
    ) -> LicenseCategory:
        """Category of a single component, honoring user overrides first."""
        if overrides:
            deemed = overrides.get(normalize_license_key(lic))
            if deemed is not None:
                return deemed
        return self._classifier.classify(lic)

    def _walk_alternatives(self, node: Any) -> list[list[str]]:
        if isinstance(node, LicenseSymbol):
            return [[self._normalize_key(str(node.key))]]
        if isinstance(node, OR):
            result: list[list[str]] = []
            for arg in node.args:
                result.extend(self._walk_alternatives(arg))
            return result
        if isinstance(node, AND):
            # Cartesian product across children: each AND child contributes
            # one branch per alternative.
            combined: list[list[str]] = [[]]
            for arg in node.args:
                child = self._walk_alternatives(arg)
                combined = [parent + branch for parent in combined for branch in child]
            return combined
        return [[]]

    @staticmethod
    def _normalize_key(key: str) -> str:
        return SpdxNormalizer.DEPRECATED_SPDX.get(key, key)
