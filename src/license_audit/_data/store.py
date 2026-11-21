"""OSADL data loading."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar

import platformdirs

VERDICTS = frozenset({"Yes", "No", "Unknown", "Check dependency", "Same"})
COPYLEFT_VALUES = frozenset({"Yes", "Yes (restricted)", "No", "Questionable"})
CORE_LICENSES = ("MIT", "Apache-2.0", "GPL-2.0-only", "GPL-3.0-only")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

_T = TypeVar("_T")


def parse_timestamp(data: dict[str, Any]) -> datetime:
    value = data.get("timestamp")
    if not isinstance(value, str):
        msg = "no timestamp"
        raise ValueError(msg)  # noqa: TRY004
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError as exc:
        msg = f"unreadable timestamp {value!r}"
        raise ValueError(msg) from exc


def matrix_rows(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    parse_timestamp(data)
    rows = {k: v for k, v in data.items() if isinstance(v, dict)}
    _require_core(rows, "no row for")
    for name, row in rows.items():
        if row.keys() != rows.keys():
            msg = f"the {name} row doesn't cover every license"
            raise ValueError(msg)
        for verdict in row.values():
            if not isinstance(verdict, str) or verdict not in VERDICTS:
                msg = f"unexpected verdict {verdict!r} in the {name} row"
                raise ValueError(msg)
    return rows


def copyleft_table(data: dict[str, Any]) -> dict[str, str]:
    parse_timestamp(data)
    table = data.get("copyleft")
    if not isinstance(table, dict):
        msg = "no copyleft table"
        raise ValueError(msg)  # noqa: TRY004
    for name, value in table.items():
        if not isinstance(value, str) or value not in COPYLEFT_VALUES:
            msg = f"unexpected copyleft value {value!r} for {name}"
            raise ValueError(msg)
    _require_core(table, "no entry for")
    return dict(table)


def _require_core(table: dict[str, Any], problem: str) -> None:
    missing = [lic for lic in CORE_LICENSES if lic not in table]
    if missing:
        msg = f"{problem} {', '.join(missing)}"
        raise ValueError(msg)


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
            self._matrix = self._load(self.MATRIX_FILE, matrix_rows)
        return self._matrix

    def copyleft(self) -> dict[str, str]:
        """Copyleft classification, keyed by SPDX id."""
        if self._copyleft is None:
            self._copyleft = self._load(self.COPYLEFT_FILE, copyleft_table)
        return self._copyleft

    def known_licenses(self) -> list[str]:
        """All license identifiers present in the matrix."""
        return list(self.matrix().keys())

    def reload(self) -> None:
        """Drop in-memory caches so the next access re-reads from disk."""
        self._matrix = None
        self._copyleft = None

    def _load(self, filename: str, parse: Callable[[dict[str, Any]], _T]) -> _T:
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
        try:
            return parse(data)
        except ValueError as exc:
            msg = f"{problem}: {exc}{hint}"
            raise ValueError(msg) from exc
