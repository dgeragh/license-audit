"""OSADL data loading."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

import platformdirs

VERDICTS = frozenset({"Yes", "No", "Unknown", "Check dependency", "Same"})
COPYLEFT_VALUES = frozenset({"Yes", "Yes (restricted)", "No", "Questionable"})
CORE_LICENSES = ("MIT", "Apache-2.0", "GPL-2.0-only", "GPL-3.0-only")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


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
    """Loads OSADL matrix and copyleft data, from the user cache when it's newer."""

    MATRIX_FILE = "osadl_matrix.json"
    COPYLEFT_FILE = "copyleft.json"

    def __init__(self) -> None:
        self._matrix: dict[str, dict[str, str]] | None = None
        self._copyleft: dict[str, str] | None = None
        self._files: dict[str, dict[str, Any]] | None = None

    def cache_dir(self) -> Path:
        """Per-user cache dir where `refresh` writes data files."""
        return Path(platformdirs.user_cache_dir("license_audit")) / "osadl"

    def matrix(self) -> dict[str, dict[str, str]]:
        """Compatibility matrix, keyed by outbound then inbound license."""
        if self._matrix is None:
            self._matrix = matrix_rows(self._file(self.MATRIX_FILE))
        return self._matrix

    def copyleft(self) -> dict[str, str]:
        """Copyleft classification, keyed by SPDX id."""
        if self._copyleft is None:
            self._copyleft = copyleft_table(self._file(self.COPYLEFT_FILE))
        return self._copyleft

    def known_licenses(self) -> list[str]:
        """All license identifiers present in the matrix."""
        return list(self.matrix().keys())

    def reload(self) -> None:
        """Drop in-memory caches so the next access re-reads from disk."""
        self._matrix = None
        self._copyleft = None
        self._files = None

    def _file(self, filename: str) -> dict[str, Any]:
        if self._files is None:
            self._files = self._select()
        return self._files[filename]

    def _select(self) -> dict[str, dict[str, Any]]:
        bundled = {name: _bundled(name) for name in _VALIDATORS}
        cached = {
            name: _parse(
                path.read_text(encoding="utf-8"),
                name,
                f"Cached {path} is not valid OSADL data",
                "; run `license-audit refresh` to replace it, or delete it to use "
                "the bundled data",
            )
            for name in _VALIDATORS
            if (path := self.cache_dir() / name).is_file()
        }
        if len(cached) == len(bundled) and parse_timestamp(
            cached[self.MATRIX_FILE]
        ) >= parse_timestamp(bundled[self.MATRIX_FILE]):
            return cached
        return bundled


_VALIDATORS: dict[str, Callable[[dict[str, Any]], object]] = {
    OSADLDataStore.MATRIX_FILE: matrix_rows,
    OSADLDataStore.COPYLEFT_FILE: copyleft_table,
}


@functools.cache
def _bundled(filename: str) -> dict[str, Any]:
    return _parse(
        resources.files("license_audit._data").joinpath(filename).read_text("utf-8"),
        filename,
        f"Bundled {filename} is not valid OSADL data",
        "; reinstall license-audit",
    )


def _parse(text: str, filename: str, problem: str, hint: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"{problem}: {exc}{hint}"
        raise ValueError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{problem}: expected a JSON object{hint}"
        raise ValueError(msg)  # noqa: TRY004
    try:
        _VALIDATORS[filename](data)
    except ValueError as exc:
        msg = f"{problem}: {exc}{hint}"
        raise ValueError(msg) from exc
    return data
