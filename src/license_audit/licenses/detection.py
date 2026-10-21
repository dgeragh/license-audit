"""License detection from package metadata."""

from __future__ import annotations

import re
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

# License classifiers that name no particular license.
_GENERIC_CLASSIFIERS = frozenset(
    {
        "License :: OSI Approved",
        "License :: DFSG approved",
        "License :: Freely Distributable",
    }
)


def unmapped_license_classifiers(meta: Message | None) -> list[str]:
    """License classifiers that name a license with no SPDX mapping.

    Detection ORs together the classifiers it can map and skips these, so a
    caller can warn that the detected license may not be the whole story.
    """
    if meta is None:
        return []
    return [
        segment
        for cls in meta.get_all("Classifier") or []
        if cls.startswith("License ::")
        and cls.strip() not in _GENERIC_CLASSIFIERS
        and (segment := cls.split("::", 1)[1].strip())
        and _normalizer.normalize_classifier(cls) is None
    ]


# A GPL-family classifier names one version and no exception, so a License
# field beside it that grants later versions or adds an exception states
# terms the classifier reading drops. Other licenses' texts often mention
# exceptions for bundled code, so only a GPL-family reading is checked.
_GPL_FAMILY = re.compile(r"\b(?:A|L)?GPL-")
_LATER_VERSIONS = re.compile(r"or[\s-]+later|any\s+later\s+version|\d\+", re.IGNORECASE)
_EXCEPTION = re.compile(r"\bexception\b", re.IGNORECASE)


def license_field_terms_dropped(meta: Message | None, expression: str) -> list[str]:
    """What a License field states that `expression`, read from classifiers,
    drops: "allows later versions", "adds an exception", or both.

    Only meaningful when `expression` came from classifiers because the
    License field couldn't be normalized.
    """
    if meta is None or not _GPL_FAMILY.search(expression):
        return []
    field = meta.get("License") or ""
    terms: list[str] = []
    if "-only" in expression and _LATER_VERSIONS.search(field):
        terms.append("allows later versions")
    if " WITH " not in expression and _EXCEPTION.search(field):
        terms.append("adds an exception")
    return terms


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

    A License-Expression is final whether or not it normalizes; the legacy
    fields are consulted only when it is absent. When a license is declared
    but cannot be normalized to SPDX, the raw string is preserved on the
    result's ``declared_license`` field rather than being discarded.
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

    PEP 639 makes License-Expression authoritative, so a stale License field
    or classifier left beside it never overrides it. Among the legacy fields a
    recognized SPDX result wins; otherwise the first one that declared
    *something* (even if unrecognized) is surfaced so its raw string isn't lost.
    """
    pep639 = _try_pep639(meta)
    if pep639 is not None:
        return pep639
    candidates = [
        candidate
        for candidate in (_try_license_field(meta), _try_classifiers(meta))
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
