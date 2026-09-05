"""OSADL data loading."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import platformdirs


class OSADLDataStore:
    """Loads OSADL matrix and copyleft data, preferring user cache over bundled files."""

    MATRIX_FILE = "osadl_matrix.json"
    COPYLEFT_FILE = "copyleft.json"

    def __init__(self) -> None:
        self._matrix: dict[str, dict[str, str]] | None = None
        self._copyleft: dict[str, str] | None = None

    def cache_dir(self) -> Path:
        """Per-user cache dir where `refresh` writes data files."""
        return Path(platformdirs.user_cache_dir("license_audit")) / "osadl"

    def matrix(self) -> dict[str, dict[str, str]]:
        """Compatibility matrix, keyed by outbound then inbound license."""
        if self._matrix is None:
            raw = self._load_json(self.MATRIX_FILE)
            self._matrix = {k: v for k, v in raw.items() if isinstance(v, dict)}
        return self._matrix

    def copyleft(self) -> dict[str, str]:
        """Copyleft classification, keyed by SPDX id."""
        if self._copyleft is None:
            raw = self._load_json(self.COPYLEFT_FILE)
            data = raw.get("copyleft", {})
            if not isinstance(data, dict):
                self._copyleft = {}
            else:
                self._copyleft = {k: v for k, v in data.items() if isinstance(v, str)}
        return self._copyleft

    def known_licenses(self) -> list[str]:
        """All license identifiers present in the matrix."""
        return list(self.matrix().keys())

    def reload(self) -> None:
        """Drop in-memory caches so the next access re-reads from disk."""
        self._matrix = None
        self._copyleft = None

    def _load_json(self, filename: str) -> dict[str, Any]:
        """Parse a data file, raising ValueError with a remedy when it's unusable."""
        cached = self.cache_dir() / filename
        if cached.is_file():
            text = cached.read_text(encoding="utf-8")
            problem = f"Cached {cached} is not valid OSADL data"
            hint = (
                "; run `license-audit refresh` to replace it, or delete it to "
                "use the bundled data"
            )
        else:
            bundled = resources.files("license_audit._data").joinpath(filename)
            text = bundled.read_text(encoding="utf-8")
            problem = f"Bundled {filename} is not valid OSADL data"
            hint = "; reinstall license-audit"
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"{problem}: {exc}{hint}"
            raise ValueError(msg) from exc
        if not isinstance(data, dict):
            msg = f"{problem}: expected a JSON object{hint}"
            raise ValueError(msg)  # noqa: TRY004
        return data
