"""Tests for the refresh CLI command."""

from __future__ import annotations

import json
from http.client import IncompleteRead
from importlib import resources
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from click.testing import CliRunner

from license_audit._data import OSADLDataStore
from license_audit._data.store import copyleft_table, matrix_rows
from license_audit.cli.main import cli
from license_audit.cli.refresh import OSADLRefresher


def _bundled(filename: str) -> bytes:
    return resources.files("license_audit._data").joinpath(filename).read_bytes()


def _payloads(url: str, parse: object) -> bytes:
    if url == OSADLRefresher.MATRIX_URL:
        return _bundled(OSADLDataStore.MATRIX_FILE)
    return _bundled(OSADLDataStore.COPYLEFT_FILE)


class TestRefreshCmd:
    def test_downloads_both_files(self, tmp_path: Path) -> None:
        store = OSADLDataStore()
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(OSADLRefresher, "fetch", side_effect=_payloads) as mock_fetch,
            patch.object(OSADLDataStore, "reload") as mock_reload,
            patch(
                "license_audit.cli.refresh.OSADLDataStore",
                return_value=store,
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 0
        assert mock_fetch.call_count == 2
        mock_reload.assert_called_once()
        assert "osadl_matrix.json updated" in result.output
        assert "copyleft.json updated" in result.output
        assert "refreshed successfully" in result.output
        assert (tmp_path / OSADLDataStore.MATRIX_FILE).read_bytes() == _bundled(
            OSADLDataStore.MATRIX_FILE
        )
        assert (tmp_path / OSADLDataStore.COPYLEFT_FILE).read_bytes() == _bundled(
            OSADLDataStore.COPYLEFT_FILE
        )

    def test_creates_cache_directory(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "sub" / "osadl"
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=cache_dir),
            patch.object(OSADLRefresher, "fetch", side_effect=_payloads),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 0
        assert cache_dir.is_dir()


class TestRefreshCmdErrors:
    def test_network_error_fails_cleanly(self, tmp_path: Path) -> None:
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(
                OSADLRefresher,
                "fetch",
                side_effect=URLError("connection refused"),
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert "Failed to refresh OSADL data" in result.output
        assert "Traceback" not in result.output

    def test_http_protocol_error_fails_cleanly(self, tmp_path: Path) -> None:
        # http.client errors are not OSError subclasses.
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(
                OSADLRefresher,
                "fetch",
                side_effect=IncompleteRead(b""),
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert "Failed to refresh OSADL data" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_oversized_response_fails_cleanly(self, tmp_path: Path) -> None:
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(
                OSADLRefresher,
                "fetch",
                side_effect=RuntimeError("response exceeds 10485760 bytes"),
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert "Failed to refresh OSADL data" in result.output

    def test_invalid_json_fails_cleanly(self, tmp_path: Path) -> None:
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(
                OSADLRefresher,
                "fetch",
                side_effect=ValueError("Invalid JSON received"),
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert "Failed to refresh OSADL data" in result.output

    def test_invalid_copyleft_download_writes_neither_file(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "osadl_matrix.json").write_bytes(b'{"old": true}')

        def fetch(url: str, parse: object) -> bytes:
            if url == OSADLRefresher.COPYLEFT_URL:
                msg = "Invalid data received"
                raise ValueError(msg)
            return _bundled(OSADLDataStore.MATRIX_FILE)

        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(OSADLRefresher, "fetch", side_effect=fetch),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert (tmp_path / "osadl_matrix.json").read_bytes() == b'{"old": true}'
        assert not (tmp_path / "copyleft.json").exists()
        assert not list(tmp_path.glob("*.tmp"))


class TestFetch:
    def _make_response(self, payload: bytes) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_valid_data(self) -> None:
        data = _bundled(OSADLDataStore.MATRIX_FILE)
        with patch(
            "license_audit.cli.refresh.urlopen",
            return_value=self._make_response(data),
        ):
            fetched = OSADLRefresher().fetch("https://example.com/m.json", matrix_rows)

        assert fetched == data

    def test_rejects_oversized_response(self) -> None:
        large = b"x" * (OSADLRefresher.MAX_RESPONSE_BYTES + 2)
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(large),
            ),
            pytest.raises(RuntimeError, match="exceeds"),
        ):
            OSADLRefresher().fetch("https://example.com/m.json", matrix_rows)

    def test_rejects_invalid_json(self) -> None:
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(b"not json at all"),
            ),
            pytest.raises(ValueError, match="Invalid JSON"),
        ):
            OSADLRefresher().fetch("https://example.com/m.json", matrix_rows)

    def test_rejects_non_object_json(self) -> None:
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(b"[1, 2]"),
            ),
            pytest.raises(ValueError, match="JSON object"),
        ):
            OSADLRefresher().fetch("https://example.com/m.json", matrix_rows)

    def test_rejects_matrix_in_another_shape(self) -> None:
        payload = json.dumps(
            {"timestamp": "2027-01-01T00:00:00+0000", "licenses": {"MIT": {}}}
        ).encode()
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(payload),
            ),
            pytest.raises(ValueError, match=r"Invalid data received.*no row for MIT"),
        ):
            OSADLRefresher().fetch("https://example.com/m.json", matrix_rows)

    def test_rejects_copyleft_in_another_shape(self) -> None:
        payload = _bundled(OSADLDataStore.MATRIX_FILE)
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(payload),
            ),
            pytest.raises(ValueError, match="no copyleft table"),
        ):
            OSADLRefresher().fetch("https://example.com/c.json", copyleft_table)

    def test_network_error(self) -> None:
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                side_effect=URLError("connection refused"),
            ),
            pytest.raises(URLError),
        ):
            OSADLRefresher().fetch("https://example.com/m.json", matrix_rows)


class TestRefreshReloadsStore:
    def test_refresh_invokes_store_reload(self, tmp_path: Path) -> None:
        store = OSADLDataStore()
        with (
            patch.object(store, "cache_dir", return_value=tmp_path),
            patch.object(store, "reload") as mock_reload,
            patch.object(OSADLRefresher, "fetch", side_effect=_payloads),
        ):
            refresher = OSADLRefresher(store=store)
            refresher.refresh(console=MagicMock())

        mock_reload.assert_called_once()
