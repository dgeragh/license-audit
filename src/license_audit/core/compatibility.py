"""License compatibility checks backed by the OSADL matrix."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from license_audit._data import OSADLDataStore
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.models import (
    CompatibilityResult,
    IncompatibleGroup,
    IncompatiblePair,
    LicenseCategory,
    Verdict,
)


@dataclass(frozen=True)
class Inbound:
    """One dependency's constraint: comply with every id of any one alternative."""

    alternatives: tuple[tuple[str, ...], ...]

    @property
    def label(self) -> str:
        parts = [" AND ".join(alt) for alt in self.alternatives]
        if len(parts) == 1:
            return parts[0]
        return " OR ".join(f"({p})" if " AND " in p else p for p in parts)


class CompatibilityMatrix:
    """Looks up inbound/outbound license compatibility from the OSADL matrix.

    The matrix answers whether code under one license can be incorporated
    into a work under another. A dependency is a separately distributed
    library, so that question only binds where copyleft reaches the combined
    work: a permissive or weak-copyleft dependency imposes nothing on a
    permissive or weak-copyleft outbound license (its obligations stay with
    its own files). A strong- or network-copyleft dependency makes the whole
    work copyleft, so it needs a strong- or network-copyleft outbound license
    the matrix allows, and every other dependency is then held to the matrix
    verdict for that license. Ids without a category keep the plain verdict.
    """

    VERDICT_MAP: dict[str, Verdict] = {
        "Yes": Verdict.COMPATIBLE,
        "No": Verdict.INCOMPATIBLE,
        "Unknown": Verdict.UNKNOWN,
        "Check dependency": Verdict.CHECK_DEPENDENCY,
        "Same": Verdict.SAME,
    }

    # "Check dependency" counts as compatible for incompatibility detection
    # (lenient: a reviewable pairing is not a definite conflict) but not for
    # recommendations, which shouldn't suggest an outbound license OSADL
    # flags for review.
    COMPATIBLE_VERDICTS: frozenset[str] = frozenset({"Yes", "Same", "Check dependency"})
    RECOMMEND_VERDICTS: frozenset[str] = frozenset({"Yes", "Same"})

    # Categories whose obligations stay with the library's own files.
    LIBRARY_SCOPED: frozenset[LicenseCategory] = frozenset(
        {LicenseCategory.PERMISSIVE, LicenseCategory.WEAK_COPYLEFT}
    )

    # OSADL marks PSF-2.0 code unusable in GPL-family works, but the FSF lists
    # the PSF License as GPL-compatible, and it is everywhere in Python
    # (typing-extensions), so its verdict there is read as "Yes".
    GPL_COMPATIBLE: frozenset[str] = frozenset({"PSF-2.0"})
    GPL_FAMILY: frozenset[str] = frozenset(
        {
            "GPL-2.0-only",
            "GPL-2.0-only WITH Classpath-exception-2.0",
            "GPL-2.0-or-later",
            "GPL-3.0-only",
            "GPL-3.0-or-later",
            "LGPL-2.0-only",
            "LGPL-2.0-or-later",
            "LGPL-2.1-only",
            "LGPL-2.1-or-later",
            "LGPL-3.0-only",
            "LGPL-3.0-or-later",
            "AGPL-3.0-only",
            "AGPL-3.0-or-later",
        }
    )

    def __init__(
        self,
        store: OSADLDataStore | None = None,
        classifier: LicenseClassifier | None = None,
    ) -> None:
        self._store = store or OSADLDataStore()
        self._classifier = classifier or LicenseClassifier(store=self._store)
        self._categories: dict[str, LicenseCategory] = {}

    def known_licenses(self) -> list[str]:
        """All licenses the matrix can answer for."""
        return self._store.known_licenses()

    def raw_verdict(self, outbound: str, inbound: str) -> str:
        """Raw OSADL string (e.g. 'Yes', 'No', 'Same').

        The matrix is indexed as matrix[outbound][inbound]. Missing rows
        or cells fall back to 'Unknown'.
        """
        if inbound in self.GPL_COMPATIBLE and outbound in self.GPL_FAMILY:
            return "Yes"
        row = self._store.matrix().get(outbound)
        if row is None:
            return "Unknown"
        return row.get(inbound, "Unknown")

    def is_compatible(self, inbound: str, outbound: str) -> CompatibilityResult:
        """Check whether a project licensed `outbound` can use a dep licensed `inbound`."""
        raw = self.raw_verdict(outbound, inbound)
        verdict = self.VERDICT_MAP.get(raw, Verdict.UNKNOWN)
        return CompatibilityResult(inbound=inbound, outbound=outbound, verdict=verdict)

    def outbound_for(self, inbound: Inbound, verdicts: frozenset[str]) -> set[str]:
        """Outbound licenses that admit every id of some alternative.

        See the class docstring for when an id is admitted. Ids absent from
        the matrix impose nothing here; they surface as UNKNOWN elsewhere.
        """
        matrix = self._store.matrix()
        result: set[str] = set()
        for alt in inbound.alternatives:
            known = [lic for lic in alt if lic in matrix]
            result.update(
                outbound
                for outbound in matrix
                if all(self._admits(outbound, lic, verdicts) for lic in known)
            )
        return result

    def _admits(self, outbound: str, inbound: str, verdicts: frozenset[str]) -> bool:
        allowed = self.raw_verdict(outbound, inbound) in verdicts
        category = self._category(inbound)
        if category in self.LIBRARY_SCOPED:
            return allowed or self._category(outbound) in self.LIBRARY_SCOPED
        if category in (
            LicenseCategory.STRONG_COPYLEFT,
            LicenseCategory.NETWORK_COPYLEFT,
        ):
            return allowed and self._category(outbound) not in self.LIBRARY_SCOPED
        return allowed

    def _category(self, lic: str) -> LicenseCategory:
        category = self._categories.get(lic)
        if category is None:
            category = self._classifier.classify(lic)
            self._categories[lic] = category
        return category

    def find_compatible_outbound(
        self,
        inbound: Iterable[Inbound],
        verdicts: frozenset[str] = RECOMMEND_VERDICTS,
    ) -> list[str]:
        """Outbound licenses that satisfy every dependency, in matrix order.

        Pass COMPATIBLE_VERDICTS for every license the compatibility check
        accepts, "Check dependency" cells included.
        """
        matrix = self._store.matrix()
        compatible = set(matrix)
        for unit in inbound:
            compatible &= self.outbound_for(unit, verdicts)
        return [lic for lic in matrix if lic in compatible]

    def find_incompatible_pairs(
        self, inbound: Iterable[Inbound]
    ) -> list[IncompatiblePair]:
        """Dependencies that share no outbound license, named by their label."""
        units = list(dict.fromkeys(inbound))
        outbound = [self.outbound_for(unit, self.COMPATIBLE_VERDICTS) for unit in units]
        pairs: list[IncompatiblePair] = []
        for i, a in enumerate(units):
            for b, outbound_b in zip(units[i + 1 :], outbound[i + 1 :], strict=True):
                if not outbound[i] & outbound_b:
                    pairs.append(IncompatiblePair(license_a=a.label, license_b=b.label))
        return pairs

    def find_incompatible_groups(
        self, inbound: Iterable[Inbound]
    ) -> list[IncompatibleGroup]:
        """A conflict no incompatible pair accounts for.

        Every pair of dependencies can share an outbound license, yet none
        satisfies them all (EUPL-1.1, Apache-2.0, and PSF-2.0), or a
        dual-licensed dependency can't be satisfied under any alternative.
        Returns one group whose every member is needed for the conflict, or
        nothing when an outbound license satisfies every dependency or a pair
        already explains why none does. So with `find_incompatible_pairs`, a
        conflict is found exactly when no outbound license passes the
        compatibility check.
        """
        units = list(dict.fromkeys(inbound))
        allowed = {u: self.outbound_for(u, self.COMPATIBLE_VERDICTS) for u in units}

        def fits(group: list[Inbound]) -> bool:
            matrix = set(self._store.matrix())
            return bool(matrix.intersection(*(allowed[u] for u in group)))

        if fits(units) or self.find_incompatible_pairs(units):
            return []
        # Drop each dependency the rest still conflict without.
        group = units
        for unit in units:
            rest = [u for u in group if u != unit]
            if not fits(rest):
                group = rest
        return [IncompatibleGroup(licenses=[unit.label for unit in group])]
