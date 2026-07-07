"""License detection from package metadata."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message

from license_audit.core.models import UNKNOWN_LICENSE, LicenseSource
from license_audit.licenses.spdx import SpdxNormalizer
from license_audit.util import MetadataReader, canonicalize

_normalizer = SpdxNormalizer()


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of detecting one package's license.

    ``expression`` is the canonical SPDX expression, or ``UNKNOWN`` when the
    license could not be recognized. ``declared_license`` holds the raw string
    that was found but could not be normalized, letting callers tell a
    *declared-but-unrecognized* license (e.g. "Proprietary License")
    apart from one that was never declared at all (``declared_license`` None).
    """

    expression: str
    source: LicenseSource
    declared_license: str | None = None

    @property
    def recognized(self) -> bool:
        """True when the license normalized to a real SPDX expression."""
        return self.expression != UNKNOWN_LICENSE


_NOT_DETECTED = DetectionResult(UNKNOWN_LICENSE, LicenseSource.UNKNOWN)


def detect_license(
    package_name: str,
    reader: MetadataReader,
    overrides: dict[str, str] | None = None,
) -> DetectionResult:
    """Detect a package's license.

    Detection order:
    1. User overrides
    2. PEP 639 License-Expression metadata field
    3. License metadata field (normalized)
    4. Trove classifiers
    5. UNKNOWN

    When a license is declared but cannot be normalized to SPDX, the raw
    string is preserved on the result's ``declared_license`` field rather than
    being discarded.
    """
    # Override keys are matched against the canonical (PEP 503) package name.
    if overrides:
        deemed = {canonicalize(name): spdx for name, spdx in overrides.items()}
        spdx = deemed.get(canonicalize(package_name))
        if spdx is not None:
            normalized = _normalizer.normalize(spdx)
            if normalized != UNKNOWN_LICENSE:
                return DetectionResult(normalized, LicenseSource.OVERRIDE)
            return DetectionResult(
                UNKNOWN_LICENSE, LicenseSource.OVERRIDE, declared_license=spdx.strip()
            )

    meta = reader.read_metadata(package_name)
    if meta is None:
        return _NOT_DETECTED

    return _detect_from_metadata(meta)


def _detect_from_metadata(meta: Message) -> DetectionResult:
    """Extract license from package metadata fields.

    Each source is consulted in priority order. A recognized SPDX result wins
    immediately; otherwise the first source that declared *something* (even if
    unrecognized) is surfaced so its raw string isn't lost.
    """
    candidates = [
        candidate
        for candidate in (
            _try_pep639(meta),
            _try_license_field(meta),
            _try_classifiers(meta),
        )
        if candidate is not None
    ]

    for candidate in candidates:
        if candidate.recognized:
            return candidate
    for candidate in candidates:
        if candidate.declared_license:
            return candidate
    return _NOT_DETECTED


def _try_pep639(meta: Message) -> DetectionResult | None:
    license_expr = meta.get("License-Expression")
    if not license_expr or license_expr.strip().upper() == UNKNOWN_LICENSE:
        return None
    normalized = _normalizer.normalize(license_expr)
    if normalized != UNKNOWN_LICENSE:
        return DetectionResult(normalized, LicenseSource.PEP639)
    return DetectionResult(
        UNKNOWN_LICENSE, LicenseSource.PEP639, declared_license=license_expr.strip()
    )


def _try_license_field(meta: Message) -> DetectionResult | None:
    license_field = meta.get("License")
    if not license_field or license_field.strip().upper() in ("UNKNOWN", "", "NONE"):
        return None
    normalized = _normalizer.normalize(license_field)
    if normalized != UNKNOWN_LICENSE:
        return DetectionResult(normalized, LicenseSource.METADATA)
    return DetectionResult(
        UNKNOWN_LICENSE, LicenseSource.METADATA, declared_license=license_field.strip()
    )


def _try_classifiers(meta: Message) -> DetectionResult | None:
    classifiers = meta.get_all("Classifier") or []
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    if not license_classifiers:
        return None

    spdx_from_classifiers: list[str] = []
    for cls in license_classifiers:
        spdx = _normalizer.normalize_classifier(cls)
        if spdx:
            spdx_from_classifiers.append(spdx)

    if len(spdx_from_classifiers) == 1:
        return DetectionResult(spdx_from_classifiers[0], LicenseSource.CLASSIFIER)
    if len(spdx_from_classifiers) > 1:
        expr = " OR ".join(sorted(set(spdx_from_classifiers)))
        return DetectionResult(expr, LicenseSource.CLASSIFIER)

    # Trove classifiers were present but none mapped to SPDX. Surface their
    # human-readable form (the segment after "License ::") so the report shows
    # what was declared, e.g. "Other/Proprietary License". Skip empty segments
    # (a bare "License ::") so they don't leave a "; " join artifact.
    declared = "; ".join(
        segment
        for cls in license_classifiers
        if (segment := cls.split("::", 1)[1].strip())
    )
    if not declared:
        return None
    return DetectionResult(
        UNKNOWN_LICENSE, LicenseSource.CLASSIFIER, declared_license=declared
    )
