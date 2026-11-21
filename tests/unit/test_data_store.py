"""Tests for OSADLDataStore."""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from license_audit._data import OSADLDataStore


def _bundled(filename: str) -> dict[str, Any]:
    text = resources.files("license_audit._data").joinpath(filename).read_text()
    data: dict[str, Any] = json.loads(text)
    return data


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[Path]:
    with patch(
        "license_audit._data.store.platformdirs.user_cache_dir",
        return_value=str(tmp_path),
    ):
        directory = tmp_path / "osadl"
        directory.mkdir()
        yield directory


class TestOSADLDataStore:
    def test_loads_bundled_matrix_by_default(self) -> None:
        store = OSADLDataStore()
        matrix = store.matrix()
        assert isinstance(matrix, dict)
        assert "MIT" in matrix

    def test_loads_bundled_copyleft_by_default(self) -> None:
        store = OSADLDataStore()
        copyleft = store.copyleft()
        assert isinstance(copyleft, dict)
        assert "MIT" in copyleft

    def test_known_licenses_matches_matrix_keys(self) -> None:
        store = OSADLDataStore()
        assert set(store.known_licenses()) == set(store.matrix().keys())

    def test_cached_matrix_overrides_bundled(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        data["MIT"]["Apache-2.0"] = "No"
        (cache / OSADLDataStore.MATRIX_FILE).write_text(json.dumps(data))

        assert OSADLDataStore().matrix()["MIT"]["Apache-2.0"] == "No"

    def test_falls_back_to_bundled_when_no_cache(self, tmp_path: Path) -> None:
        with patch(
            "license_audit._data.store.platformdirs.user_cache_dir",
            return_value=str(tmp_path),
        ):
            store = OSADLDataStore()
            matrix = store.matrix()
        assert isinstance(matrix, dict)
        assert len(matrix) > 0

    def test_reload_invalidates_cache(self, cache: Path) -> None:
        cache_file = cache / OSADLDataStore.MATRIX_FILE
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        data["MIT"]["Apache-2.0"] = "No"
        cache_file.write_text(json.dumps(data))

        store = OSADLDataStore()
        assert store.matrix()["MIT"]["Apache-2.0"] == "No"

        data["MIT"]["Apache-2.0"] = "Unknown"
        cache_file.write_text(json.dumps(data))
        assert store.matrix()["MIT"]["Apache-2.0"] == "No"
        store.reload()
        assert store.matrix()["MIT"]["Apache-2.0"] == "Unknown"

    def test_cache_dir_under_user_cache(self) -> None:
        store = OSADLDataStore()
        assert store.cache_dir().name == "osadl"


class TestCorruptCache:
    """A bad cache file must name itself and the remedy, not crash every command."""

    def _store_with_cache(self, tmp_path: Path, filename: str, text: str) -> Path:
        cache_file = tmp_path / "osadl" / filename
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(text)
        return cache_file

    def test_malformed_json(self, tmp_path: Path) -> None:
        cache_file = self._store_with_cache(
            tmp_path, OSADLDataStore.MATRIX_FILE, "not json"
        )
        with (
            patch(
                "license_audit._data.store.platformdirs.user_cache_dir",
                return_value=str(tmp_path),
            ),
            pytest.raises(ValueError, match="refresh") as excinfo,
        ):
            OSADLDataStore().matrix()
        assert str(cache_file) in str(excinfo.value)

    def test_non_object_json(self, tmp_path: Path) -> None:
        self._store_with_cache(tmp_path, OSADLDataStore.MATRIX_FILE, "[1, 2]")
        with (
            patch(
                "license_audit._data.store.platformdirs.user_cache_dir",
                return_value=str(tmp_path),
            ),
            pytest.raises(ValueError, match="JSON object"),
        ):
            OSADLDataStore().matrix()

    def test_copyleft_file_checked_too(self, tmp_path: Path) -> None:
        self._store_with_cache(tmp_path, OSADLDataStore.COPYLEFT_FILE, "null")
        with (
            patch(
                "license_audit._data.store.platformdirs.user_cache_dir",
                return_value=str(tmp_path),
            ),
            pytest.raises(ValueError, match="JSON object"),
        ):
            OSADLDataStore().copyleft()


class TestInvalidData:
    def test_matrix_with_another_shape_is_rejected(self, cache: Path) -> None:
        cache_file = cache / OSADLDataStore.MATRIX_FILE
        cache_file.write_text(
            json.dumps(
                {
                    "timestamp": "2027-01-01T00:00:00+0000",
                    "licenses": {"MIT": {"MIT": "Same"}},
                }
            )
        )
        with pytest.raises(ValueError, match="refresh") as excinfo:
            OSADLDataStore().matrix()
        assert str(cache_file) in str(excinfo.value)
        assert "no row for MIT" in str(excinfo.value)

    def test_matrix_without_timestamp_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        del data["timestamp"]
        (cache / OSADLDataStore.MATRIX_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match="no timestamp"):
            OSADLDataStore().matrix()

    def test_matrix_with_unreadable_timestamp_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        data["timestamp"] = "yesterday"
        (cache / OSADLDataStore.MATRIX_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match="unreadable timestamp"):
            OSADLDataStore().matrix()

    def test_matrix_row_missing_a_license_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        del data["MIT"]["Apache-2.0"]
        (cache / OSADLDataStore.MATRIX_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match="MIT row doesn't cover every license"):
            OSADLDataStore().matrix()

    def test_matrix_with_unknown_verdict_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        data["MIT"]["Apache-2.0"] = "Maybe"
        (cache / OSADLDataStore.MATRIX_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match="unexpected verdict 'Maybe'"):
            OSADLDataStore().matrix()

    def test_copyleft_without_table_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.COPYLEFT_FILE)
        data["licenses"] = data.pop("copyleft")
        (cache / OSADLDataStore.COPYLEFT_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match="no copyleft table"):
            OSADLDataStore().copyleft()

    def test_copyleft_with_unknown_value_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.COPYLEFT_FILE)
        data["copyleft"]["MIT"] = False
        (cache / OSADLDataStore.COPYLEFT_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match="unexpected copyleft value False"):
            OSADLDataStore().copyleft()

    def test_copyleft_missing_core_license_is_rejected(self, cache: Path) -> None:
        data = _bundled(OSADLDataStore.COPYLEFT_FILE)
        del data["copyleft"]["GPL-3.0-only"]
        (cache / OSADLDataStore.COPYLEFT_FILE).write_text(json.dumps(data))
        with pytest.raises(ValueError, match=r"no entry for GPL-3\.0-only"):
            OSADLDataStore().copyleft()
