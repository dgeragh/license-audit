"""License compatibility engine using the OSADL matrix."""

from __future__ import annotations

from license_audit._data import OSADLDataStore
from license_audit.core.models import CompatibilityResult, Verdict


class CompatibilityMatrix:
    """Query the OSADL license compatibility matrix."""

    VERDICT_MAP: dict[str, Verdict] = {
        "Yes": Verdict.COMPATIBLE,
        "No": Verdict.INCOMPATIBLE,
        "Unknown": Verdict.UNKNOWN,
        "Check dependency": Verdict.CHECK_DEPENDENCY,
        "Same": Verdict.SAME,
    }

    COMPATIBLE_VERDICTS: frozenset[str] = frozenset({"Yes", "Same", "Check dependency"})

    def __init__(self, store: OSADLDataStore | None = None) -> None:
        self._store = store or OSADLDataStore()

    def known_licenses(self) -> list[str]:
        """Return the list of licenses known to the OSADL matrix."""
        return self._store.known_licenses()

    def raw_verdict(self, outbound: str, inbound: str) -> str:
        """Look up the raw OSADL verdict string.

        The matrix is indexed as matrix[outbound][inbound]. Missing entries
        fall back to ``"Unknown"``.
        """
        row = self._store.matrix().get(outbound)
        if row is None:
            return "Unknown"
        return row.get(inbound, "Unknown")

    def is_compatible(self, inbound: str, outbound: str) -> CompatibilityResult:
        """Return the compatibility verdict for an inbound-outbound pair."""
        raw = self.raw_verdict(outbound, inbound)
        verdict = self.VERDICT_MAP.get(raw, Verdict.UNKNOWN)
        return CompatibilityResult(inbound=inbound, outbound=outbound, verdict=verdict)

    def find_compatible_outbound(self, inbound_licenses: list[str]) -> list[str]:
        """Return every outbound license compatible with all evaluable inbound licenses.

        Inbound licenses absent from the matrix are skipped; they cannot
        constrain the recommendation and are surfaced separately as UNKNOWN.
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
                self.raw_verdict(outbound, inbound) in self.COMPATIBLE_VERDICTS
                for inbound in evaluable
            )
        ]

    def find_incompatible_pairs(self, licenses: list[str]) -> list[CompatibilityResult]:
        """Return pairs of licenses that no outbound license can accommodate together."""
        matrix = self._store.matrix()
        evaluable = [lic for lic in licenses if lic in matrix]
        all_outbound = list(matrix.keys())

        results: list[CompatibilityResult] = []
        for i, lic_a in enumerate(evaluable):
            for lic_b in evaluable[i + 1 :]:
                has_common = any(
                    self.raw_verdict(outbound, lic_a) in self.COMPATIBLE_VERDICTS
                    and self.raw_verdict(outbound, lic_b) in self.COMPATIBLE_VERDICTS
                    for outbound in all_outbound
                )
                if not has_common:
                    results.append(
                        CompatibilityResult(
                            inbound=lic_a,
                            outbound=lic_b,
                            verdict=Verdict.INCOMPATIBLE,
                        )
                    )
        return results
