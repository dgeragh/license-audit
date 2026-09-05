"""License compatibility checks backed by the OSADL matrix."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from license_audit._data import OSADLDataStore
from license_audit.core.models import CompatibilityResult, IncompatiblePair, Verdict


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

    def outbound_for(self, inbound: Inbound, verdicts: frozenset[str]) -> set[str]:
        """Outbound licenses whose verdicts for some alternative all fall in `verdicts`.

        Ids absent from the matrix impose nothing here; they surface as
        UNKNOWN elsewhere.
        """
        matrix = self._store.matrix()
        result: set[str] = set()
        for alt in inbound.alternatives:
            known = [lic for lic in alt if lic in matrix]
            result.update(
                outbound
                for outbound in matrix
                if all(self.raw_verdict(outbound, lic) in verdicts for lic in known)
            )
        return result

    def find_compatible_outbound(self, inbound: Iterable[Inbound]) -> list[str]:
        """Outbound licenses that satisfy every dependency, in matrix order."""
        matrix = self._store.matrix()
        compatible = set(matrix)
        for unit in inbound:
            compatible &= self.outbound_for(unit, self.RECOMMEND_VERDICTS)
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
