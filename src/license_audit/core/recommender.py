"""Recommend outbound licenses compatible with a set of dependencies."""

from __future__ import annotations

import math

from license_audit.core.classifier import LicenseClassifier
from license_audit.core.compatibility import CompatibilityMatrix
from license_audit.core.models import CATEGORY_RANK, UNKNOWN_LICENSE, LicenseCategory
from license_audit.licenses.expression import ExpressionEvaluator
from license_audit.licenses.spdx import SpdxNormalizer


class LicenseRecommender:
    """Picks compatible outbound licenses ranked by permissiveness.

    Within each category there are dozens of pairwise-compatible SPDX ids,
    so a pure category sort with an alphabetical tiebreaker surfaces
    obscure picks (Apache-1.0, Artistic-1.0-Perl) ahead of mainstream
    ones. ``PREFERRED`` is a curated shortlist used as the tiebreaker:
    licenses listed here come first in the order shown, then everything
    else falls back to alphabetical inside its category.
    """

    PREFERRED: list[str] = [
        # Permissive
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Unlicense",
        # Weak copyleft
        "MPL-2.0",
        "LGPL-3.0-only",
        "LGPL-2.1-only",
        # Strong copyleft
        "GPL-3.0-only",
        "GPL-2.0-only",
        # Network copyleft
        "AGPL-3.0-only",
    ]

    def __init__(
        self,
        matrix: CompatibilityMatrix | None = None,
        classifier: LicenseClassifier | None = None,
        normalizer: SpdxNormalizer | None = None,
        expression: ExpressionEvaluator | None = None,
    ) -> None:
        self._matrix = matrix or CompatibilityMatrix()
        self._classifier = classifier or LicenseClassifier()
        self._normalizer = normalizer or SpdxNormalizer(matrix=self._matrix)
        self._expression = expression or ExpressionEvaluator(
            classifier=self._classifier,
            normalizer=self._normalizer,
        )
        self._preferred_index = {name: i for i, name in enumerate(self.PREFERRED)}

    def recommend(self, dependency_licenses: list[str]) -> list[str]:
        """Compatible outbound licenses, most permissive first."""
        resolved = self.resolve_inbound(dependency_licenses)
        if not resolved:
            return self._default_recommendations()

        compatible = self._matrix.find_compatible_outbound(resolved)
        return sorted(compatible, key=self._sort_key)

    def _sort_key(self, lic: str) -> tuple[int, float, str]:
        category_rank = CATEGORY_RANK.get(self._classifier.classify(lic), 5)
        preference = self._preferred_index.get(lic, math.inf)
        return (category_rank, preference, lic)

    def _default_recommendations(self) -> list[str]:
        return [
            lic
            for lic in self.PREFERRED
            if self._classifier.classify(lic) == LicenseCategory.PERMISSIVE
        ]

    def find_minimum(self, dependency_licenses: list[str]) -> str | None:
        """The single most permissive compatible outbound license, or None."""
        recommended = self.recommend(dependency_licenses)
        if not recommended:
            return None
        return recommended[0]

    def resolve_inbound(self, expressions: list[str]) -> list[str]:
        """Flatten SPDX expressions into a deduplicated list of licenses.

        Each expression resolves through ExpressionEvaluator.required_ids —
        the same OR/AND semantics the compatibility check uses — so the
        recommendation can't contradict the incompatible-pair results.
        UNKNOWN is dropped.
        """
        resolved: set[str] = set()
        for expr in expressions:
            if expr == UNKNOWN_LICENSE:
                continue
            resolved.update(self._expression.required_ids(expr))
        return list(resolved)
