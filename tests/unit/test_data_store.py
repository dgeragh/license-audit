"""Tests for OSADLDataStore."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from license_audit._data import OSADLDataStore


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

    def test_cached_matrix_overrides_bundled(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "osadl" / OSADLDataStore.MATRIX_FILE
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({"CustomLicense": {"MIT": "Yes"}}))

        with patch(
            "license_audit._data.store.platformdirs.user_cache_dir",
            return_value=str(tmp_path),
        ):
            store = OSADLDataStore()
            assert store.matrix() == {"CustomLicense": {"MIT": "Yes"}}

    def test_falls_back_to_bundled_when_no_cache(self, tmp_path: Path) -> None:
        with patch(
            "license_audit._data.store.platformdirs.user_cache_dir",
            return_value=str(tmp_path),
        ):
            store = OSADLDataStore()
            matrix = store.matrix()
        assert isinstance(matrix, dict)
        assert len(matrix) > 0

    def test_reload_invalidates_cache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "osadl"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / OSADLDataStore.MATRIX_FILE
        cache_file.write_text(json.dumps({"First": {}}))

        with patch(
            "license_audit._data.store.platformdirs.user_cache_dir",
            return_value=str(tmp_path),
        ):
            store = OSADLDataStore()
            assert "First" in store.matrix()

            cache_file.write_text(json.dumps({"Second": {}}))
            assert "First" in store.matrix()  # still cached
            store.reload()
            assert "Second" in store.matrix()

    def test_cache_dir_under_user_cache(self) -> None:
        store = OSADLDataStore()
        assert store.cache_dir().name == "osadl"
