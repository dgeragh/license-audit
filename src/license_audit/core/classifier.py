"""License classification using OSADL copyleft data."""

from __future__ import annotations

from license_audit._data import OSADLDataStore
from license_audit.core.models import LicenseCategory


class LicenseClassifier:
    """Maps SPDX license IDs to a LicenseCategory using OSADL copyleft data."""

    COPYLEFT_MAP: dict[str, LicenseCategory] = {
        "Yes": LicenseCategory.STRONG_COPYLEFT,
        "Yes (restricted)": LicenseCategory.WEAK_COPYLEFT,
        "No": LicenseCategory.PERMISSIVE,
        "Questionable": LicenseCategory.UNKNOWN,
    }

    NETWORK_COPYLEFT: frozenset[str] = frozenset({
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "AGPL-1.0-only",
        "AGPL-1.0-or-later",
    })

    def __init__(self, store: OSADLDataStore | None = None) -> None:
        self._store = store or OSADLDataStore()

    def classify(self, spdx_id: str) -> LicenseCategory:
        """Classify an SPDX license by its copyleft strength.

        A `X WITH exception` form absent from the OSADL data falls back to
        the base license: exceptions only grant extra permissions, so the
        base category is a safe upper bound.
        """
        if self.is_network_copyleft(spdx_id):
            return LicenseCategory.NETWORK_COPYLEFT

        raw_value = self._store.copyleft().get(spdx_id)
        if raw_value is not None:
            return self.COPYLEFT_MAP.get(raw_value, LicenseCategory.UNKNOWN)

        if " WITH " in spdx_id:
            return self.classify(spdx_id.split(" WITH ", 1)[0])

        return LicenseCategory.UNKNOWN

    def is_network_copyleft(self, spdx_id: str) -> bool:
        """True for the AGPL family."""
        return spdx_id in self.NETWORK_COPYLEFT
