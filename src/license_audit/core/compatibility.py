"""License compatibility checks backed by the OSADL matrix."""

from __future__ import annotations

from license_audit._data import OSADLDataStore
from license_audit.core.models import CompatibilityResult, IncompatiblePair, Verdict


class CompatibilityMatrix:
    """Looks up inbound/outbound license compatibility from the OSADL matrix."""

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

    def __init__(self, store: OSADLDataStore | None = None) -> None:
        self._store = store or OSADLDataStore()

    def known_licenses(self) -> list[str]:
        """All licenses the matrix can answer for."""
        return self._store.known_licenses()

    def raw_verdict(self, outbound: str, inbound: str) -> str:
        """Raw OSADL string (e.g. 'Yes', 'No', 'Same').

        The matrix is indexed as matrix[outbound][inbound]. Missing rows
        or cells fall back to 'Unknown'.
        """
        row = self._store.matrix().get(outbound)
        if row is None:
            return "Unknown"
        return row.get(inbound, "Unknown")

    def is_compatible(self, inbound: str, outbound: str) -> CompatibilityResult:
        """Check whether a project licensed `outbound` can use a dep licensed `inbound`."""
        raw = self.raw_verdict(outbound, inbound)
        verdict = self.VERDICT_MAP.get(raw, Verdict.UNKNOWN)
        return CompatibilityResult(inbound=inbound, outbound=outbound, verdict=verdict)

    def find_compatible_outbound(self, inbound_licenses: list[str]) -> list[str]:
        """Outbound licenses compatible with every evaluable inbound license.

        Inbounds absent from the matrix are skipped; those surface as UNKNOWN
        elsewhere so they don't block the recommendation here.
        """
        matrix = self._store.matrix()
        all_outbound = list(matrix.keys())
        evaluable = [lic for lic in inbound_licenses if lic in matrix]

        if not evaluable:
            return all_outbound

        return [
            outbound
            for outbound in all_outbound
            if all(
                self.raw_verdict(outbound, inbound) in self.RECOMMEND_VERDICTS
                for inbound in evaluable
            )
        ]

    def find_incompatible_pairs(self, licenses: list[str]) -> list[IncompatiblePair]:
        """Pairs of licenses with no common outbound license."""
        matrix = self._store.matrix()
        evaluable = [lic for lic in licenses if lic in matrix]
        all_outbound = list(matrix.keys())

        results: list[IncompatiblePair] = []
        for i, lic_a in enumerate(evaluable):
            for lic_b in evaluable[i + 1 :]:
                has_common = any(
                    self.raw_verdict(outbound, lic_a) in self.COMPATIBLE_VERDICTS
                    and self.raw_verdict(outbound, lic_b) in self.COMPATIBLE_VERDICTS
                    for outbound in all_outbound
                )
                if not has_common:
                    results.append(IncompatiblePair(license_a=lic_a, license_b=lic_b))
        return results
