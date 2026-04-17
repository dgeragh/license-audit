"""SPDX license expression normalization.

Handles the messy reality of PyPI license strings and normalizes them
to proper SPDX identifiers using the license-expression library.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from license_expression import ExpressionError, Licensing

from license_audit.core.models import UNKNOWN_LICENSE

_licensing = Licensing()

# Common non-SPDX strings found on PyPI -> SPDX identifiers
_COMMON_ALIASES: dict[str, str] = {
    # BSD variants
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "bsd-3": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "3-clause bsd": "BSD-3-Clause",
    "modified bsd": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd-2": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "freebsd": "BSD-2-Clause",
    # MIT variants
    "mit": "MIT",
    "mit license": "MIT",
    "the mit license": "MIT",
    "mit/x11": "MIT",
    # Apache variants
    "apache": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache software license 2.0": "Apache-2.0",
    # GPL variants
    "gpl": "GPL-3.0-only",
    "gpl v2": "GPL-2.0-only",
    "gpl v3": "GPL-3.0-only",
    "gpl-2": "GPL-2.0-only",
    "gpl-3": "GPL-3.0-only",
    "gplv2": "GPL-2.0-only",
    "gplv3": "GPL-3.0-only",
    "gnu gpl": "GPL-3.0-only",
    "gnu gpl v2": "GPL-2.0-only",
    "gnu gpl v3": "GPL-3.0-only",
    "gnu general public license v2 (gplv2)": "GPL-2.0-only",
    "gnu general public license v3 (gplv3)": "GPL-3.0-only",
    "gnu general public license v2 or later (gplv2+)": "GPL-2.0-or-later",
    "gnu general public license v3 or later (gplv3+)": "GPL-3.0-or-later",
    # LGPL variants
    "lgpl": "LGPL-3.0-only",
    "lgpl v2": "LGPL-2.1-only",
    "lgpl v3": "LGPL-3.0-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-3": "LGPL-3.0-only",
    "gnu lesser general public license v2 (lgplv2)": "LGPL-2.1-only",
    "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0-only",
    "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.1-or-later",
    "gnu lesser general public license v3 or later (lgplv3+)": "LGPL-3.0-or-later",
    # MPL
    "mpl": "MPL-2.0",
    "mpl 2.0": "MPL-2.0",
    "mpl-2": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    # ISC
    "isc": "ISC",
    "isc license": "ISC",
    # PSF
    "psf": "PSF-2.0",
    "psf license": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    # Unlicense
    "unlicense": "Unlicense",
    "the unlicense": "Unlicense",
    # Public domain
    "public domain": "Unlicense",
    # CC0
    "cc0": "CC0-1.0",
    "cc0 1.0": "CC0-1.0",
    "cc0-1.0": "CC0-1.0",
}

# Deprecated SPDX IDs -> current equivalents.
# The license-expression library parses these successfully, but the OSADL
# matrix uses the modern "-only"/"-or-later" forms.
_DEPRECATED_SPDX: dict[str, str] = {
    "GPL-1.0": "GPL-1.0-only",
    "GPL-1.0+": "GPL-1.0-or-later",
    "GPL-2.0": "GPL-2.0-only",
    "GPL-2.0+": "GPL-2.0-or-later",
    "GPL-3.0": "GPL-3.0-only",
    "GPL-3.0+": "GPL-3.0-or-later",
    "LGPL-2.0": "LGPL-2.0-only",
    "LGPL-2.0+": "LGPL-2.0-or-later",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-2.1+": "LGPL-2.1-or-later",
    "LGPL-3.0": "LGPL-3.0-only",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "AGPL-1.0": "AGPL-1.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
    "AGPL-3.0+": "AGPL-3.0-or-later",
}

# Trove classifier -> SPDX
_CLASSIFIER_MAP: dict[str, str] = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)": "GPL-2.0-or-later",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.1-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0-only",
    "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0-or-later",
    "License :: OSI Approved :: European Union Public Licence 1.2 (EUPL 1.2)": "EUPL-1.2",
    "License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)": "EPL-2.0",
    "License :: OSI Approved :: Artistic License": "Artistic-2.0",
    "License :: OSI Approved :: zlib/libpng License": "Zlib",
    "License :: OSI Approved :: Academic Free License (AFL)": "AFL-3.0",
    "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "License :: Public Domain": "Unlicense",
}


@lru_cache(maxsize=1)
def _known_spdx_ids() -> frozenset[str]:
    """Return the set of SPDX identifiers we can actually evaluate.

    Combines OSADL matrix keys with targets from our alias/classifier maps
    so that e.g. CC0-1.0 is recognized even if absent from the matrix.
    """
    from license_audit.core.compatibility import CompatibilityMatrix

    ids: set[str] = set(CompatibilityMatrix().known_licenses())
    ids.update(_COMMON_ALIASES.values())
    ids.update(v for v in _CLASSIFIER_MAP.values())
    ids.update(_DEPRECATED_SPDX.values())
    return frozenset(ids)


def normalize(license_string: str) -> str:
    """Normalize a license string to an SPDX expression.

    Tries in order:
    1. Lookup in common aliases table (case-insensitive) - catches messy PyPI strings
    2. Direct parse as valid SPDX expression - for well-formed SPDX
    3. Return "UNKNOWN"
    """
    stripped = license_string.strip()
    if not stripped or stripped.upper() in (UNKNOWN_LICENSE, "NONE", ""):
        return UNKNOWN_LICENSE

    # Try alias lookup first (handles "BSD License", "Apache Software License", etc.)
    alias_result = _COMMON_ALIASES.get(stripped.lower())
    if alias_result:
        return alias_result

    # Try direct SPDX parse
    try:
        parsed: Any = _licensing.parse(stripped)
        # Validate that every symbol in the expression is a recognized license.
        # The license-expression library accepts arbitrary strings as license
        # keys, so "Dual License" parses successfully despite not being SPDX.
        symbols = [str(sym.key) for sym in parsed.symbols]
        known = _known_spdx_ids()
        if all(_DEPRECATED_SPDX.get(s, s) in known for s in symbols):
            result = str(parsed)
            return _DEPRECATED_SPDX.get(result, result)
    except ExpressionError:
        pass

    return UNKNOWN_LICENSE


def normalize_classifier(classifier: str) -> str | None:
    """Convert a trove classifier to an SPDX identifier, or None if unknown."""
    return _CLASSIFIER_MAP.get(classifier)


def parse_expression(expr: str) -> Any:
    """Parse an SPDX expression, returning None on failure."""
    try:
        return _licensing.parse(expr)
    except ExpressionError:
        return None


def get_simple_licenses(expr: str) -> list[str]:
    """Extract individual license identifiers from a compound expression.

    For "MIT OR Apache-2.0" returns ["MIT", "Apache-2.0"].
    For "MIT" returns ["MIT"].
    For unparseable strings returns [expr] as-is.

    Deprecated SPDX IDs are mapped to their current equivalents.
    """
    parsed = parse_expression(expr)
    if parsed is None:
        return [expr]
    return [_DEPRECATED_SPDX.get(str(sym.key), str(sym.key)) for sym in parsed.symbols]
