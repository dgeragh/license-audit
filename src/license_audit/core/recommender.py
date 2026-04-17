"""License recommendation engine.

Given a set of dependency licenses, determines valid outbound licenses
and ranks them by permissiveness.
"""

from __future__ import annotations

from license_audit.core.classifier import LicenseClassifier
from license_audit.core.compatibility import CompatibilityMatrix
from license_audit.core.models import CATEGORY_RANK, UNKNOWN_LICENSE
from license_audit.licenses.spdx import get_simple_licenses

_classifier = LicenseClassifier()
_matrix = CompatibilityMatrix()

_PREFERRED_PERMISSIVE = [
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "Unlicense",
]


def recommend_licenses(
    dependency_licenses: list[str],
) -> list[str]:
    """Recommend outbound licenses based on dependency licenses.

    Resolves OR expressions by picking the most permissive alternative,
    then finds all compatible outbound licenses, sorted by permissiveness.

    Args:
        dependency_licenses: SPDX expressions of all dependencies.

    Returns:
        List of valid outbound SPDX license identifiers, sorted from
        most permissive to least permissive.
    """
    # Resolve compound expressions to simple license lists
    resolved = _resolve_inbound(dependency_licenses)

    if not resolved:
        # No dependencies, everything is available
        return _PREFERRED_PERMISSIVE.copy()

    compatible = _matrix.find_compatible_outbound(resolved)

    # Sort by permissiveness, then alphabetically
    return sorted(
        compatible,
        key=lambda lic: (CATEGORY_RANK.get(_classifier.classify(lic), 5), lic),
    )


def find_minimum_license(dependency_licenses: list[str]) -> str | None:
    """Find the most permissive outbound license that satisfies all dependencies.

    Returns None if no compatible license exists (conflicting deps).
    """
    recommended = recommend_licenses(dependency_licenses)
    if not recommended:
        return None
    return recommended[0]


def _resolve_inbound(expressions: list[str]) -> list[str]:
    """Resolve a list of SPDX expressions to individual licenses.

    For OR expressions, picks the most permissive alternative.
    For AND expressions, includes all components.
    Deduplicates the result.
    """
    resolved: set[str] = set()
    for expr in expressions:
        if expr == UNKNOWN_LICENSE:
            continue

        simple = get_simple_licenses(expr)
        if len(simple) == 1:
            resolved.add(simple[0])
        elif " OR " in expr:
            # Pick the most permissive alternative
            best = min(
                simple,
                key=lambda lic: CATEGORY_RANK.get(_classifier.classify(lic), 5),
            )
            resolved.add(best)
        else:
            # AND: include all
            resolved.update(simple)

    return list(resolved)
