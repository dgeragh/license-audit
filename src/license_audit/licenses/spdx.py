"""Normalize messy PyPI license strings into SPDX identifiers."""

from __future__ import annotations

from typing import Any

from license_expression import ExpressionError, Licensing, get_spdx_licensing

from license_audit.core.compatibility import CompatibilityMatrix
from license_audit.core.models import UNKNOWN_LICENSE


class SpdxNormalizer:
    """Converts loose license strings into canonical SPDX identifiers."""

    # Non-SPDX strings commonly found on PyPI mapped to their SPDX equivalents.
    COMMON_ALIASES: dict[str, str] = {
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

    # Deprecated SPDX IDs mapped to the modern "-only"/"-or-later" forms used
    # by the OSADL matrix. license-expression still parses the old forms.
    DEPRECATED_SPDX: dict[str, str] = {
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

    # Trove classifiers mapped to SPDX identifiers.
    CLASSIFIER_MAP: dict[str, str] = {
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

    def __init__(self, matrix: CompatibilityMatrix | None = None) -> None:
        self._matrix = matrix or CompatibilityMatrix()
        self._licensing = Licensing()
        self._known_ids: frozenset[str] | None = None
        self._spdx_licensing: Any = None

    def known_spdx_ids(self) -> frozenset[str]:
        """SPDX ids recognized as valid.

        Combines the matrix keys with the values in our alias, classifier,
        and deprecated-id maps so ids like CC0-1.0 are still recognized
        even when they're absent from the matrix.
        """
        if self._known_ids is None:
            ids: set[str] = set(self._matrix.known_licenses())
            ids.update(self.COMMON_ALIASES.values())
            ids.update(self.CLASSIFIER_MAP.values())
            ids.update(self.DEPRECATED_SPDX.values())
            self._known_ids = frozenset(ids)
        return self._known_ids

    def _spdx(self) -> Any:
        if self._spdx_licensing is None:
            self._spdx_licensing = get_spdx_licensing()
        return self._spdx_licensing

    def normalize(self, license_string: str) -> str:
        """Normalize a license string to an SPDX expression, or UNKNOWN.

        Tries the alias table first (case-insensitive), then validation
        against the full SPDX license list, then falls back to parsing
        with the ids from ``known_spdx_ids()``.
        """
        stripped = license_string.strip()
        if not stripped or stripped.upper() in (UNKNOWN_LICENSE, "NONE", ""):
            return UNKNOWN_LICENSE

        alias_result = self.COMMON_ALIASES.get(stripped.lower())
        if alias_result:
            return alias_result

        # validate() raises AttributeError on truncated input like "MIT AND".
        try:
            info = self._spdx().validate(stripped)
        except (AttributeError, ExpressionError):
            info = None
        if info is not None and not info.errors and info.normalized_expression:
            return str(info.normalized_expression)

        try:
            parsed: Any = self._licensing.parse(stripped)
            symbols = [str(sym.key) for sym in parsed.symbols]
            known = self.known_spdx_ids()
            if all(self.DEPRECATED_SPDX.get(s, s) in known for s in symbols):
                result = str(parsed)
                return self.DEPRECATED_SPDX.get(result, result)
        except ExpressionError:
            pass

        return UNKNOWN_LICENSE

    def normalize_classifier(self, classifier: str) -> str | None:
        """SPDX id for a trove classifier, or None if no mapping exists."""
        return self.CLASSIFIER_MAP.get(classifier)

    def parse_expression(self, expr: str) -> Any:
        """Parse an SPDX expression into an AST, or None on failure."""
        try:
            return self._licensing.parse(expr)
        except ExpressionError:
            return None

    def get_simple_licenses(self, expr: str) -> list[str]:
        """Split a compound expression into its component license ids.

        Deprecated ids are promoted to their modern equivalents. If the
        expression can't be parsed, returns it unchanged as a single-item list.
        """
        parsed = self.parse_expression(expr)
        if parsed is None:
            return [expr]
        return [
            self.DEPRECATED_SPDX.get(str(sym.key), str(sym.key))
            for sym in parsed.symbols
        ]
