"""Tests for the refresh CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from click.testing import CliRunner

from license_audit._data import OSADLDataStore
from license_audit.cli.main import cli
from license_audit.cli.refresh import OSADLRefresher


class TestRefreshCmd:
    def test_downloads_both_files(self, tmp_path: Path) -> None:
        store = OSADLDataStore()
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(OSADLRefresher, "download") as mock_dl,
            patch.object(OSADLDataStore, "reload") as mock_reload,
            patch(
                "license_audit.cli.refresh.OSADLDataStore",
                return_value=store,
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 0
        assert mock_dl.call_count == 2
        mock_reload.assert_called_once()
        assert "matrix.json updated" in result.output
        assert "copyleft.json updated" in result.output
        assert "refreshed successfully" in result.output

    def test_creates_cache_directory(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "sub" / "osadl"
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=cache_dir),
            patch.object(OSADLRefresher, "download"),
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
                "download",
                side_effect=URLError("connection refused"),
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert "Failed to refresh OSADL data" in result.output
        assert "Traceback" not in result.output

    def test_oversized_response_fails_cleanly(self, tmp_path: Path) -> None:
        with (
            patch.object(OSADLDataStore, "cache_dir", return_value=tmp_path),
            patch.object(
                OSADLRefresher,
                "download",
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
                "download",
                side_effect=ValueError("Invalid JSON received"),
            ),
        ):
            result = CliRunner().invoke(cli, ["refresh"])

        assert result.exit_code == 1
        assert "Failed to refresh OSADL data" in result.output


class TestDownload:
    def _make_response(self, payload: bytes) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        data = json.dumps({"key": "value"}).encode()
        dest = tmp_path / "test.json"
        with patch(
            "license_audit.cli.refresh.urlopen",
            return_value=self._make_response(data),
        ):
            OSADLRefresher().download("https://example.com/test.json", dest)

        assert dest.exists()
        assert json.loads(dest.read_text()) == {"key": "value"}

    def test_rejects_oversized_response(self, tmp_path: Path) -> None:
        large = b"x" * (OSADLRefresher.MAX_RESPONSE_BYTES + 2)
        dest = tmp_path / "test.json"
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(large),
            ),
            pytest.raises(RuntimeError, match="exceeds"),
        ):
            OSADLRefresher().download("https://example.com/test.json", dest)

        assert not dest.exists()

    def test_rejects_invalid_json(self, tmp_path: Path) -> None:
        dest = tmp_path / "test.json"
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(b"not json at all"),
            ),
            pytest.raises(ValueError, match="Invalid JSON"),
        ):
            OSADLRefresher().download("https://example.com/test.json", dest)

    def test_network_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "test.json"
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                side_effect=URLError("connection refused"),
            ),
            pytest.raises(URLError),
        ):
            OSADLRefresher().download("https://example.com/test.json", dest)

    def test_failed_download_preserves_existing_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "test.json"
        dest.write_bytes(b'{"old": true}')
        with (
            patch(
                "license_audit.cli.refresh.urlopen",
                return_value=self._make_response(b"not json at all"),
            ),
            pytest.raises(ValueError, match="Invalid JSON"),
        ):
            OSADLRefresher().download("https://example.com/test.json", dest)

        assert json.loads(dest.read_text()) == {"old": True}
        assert not (tmp_path / "test.json.tmp").exists()


class TestRefreshReloadsStore:
    def test_refresh_invokes_store_reload(self, tmp_path: Path) -> None:
        store = OSADLDataStore()
        with (
            patch.object(store, "cache_dir", return_value=tmp_path),
            patch.object(store, "reload") as mock_reload,
            patch.object(OSADLRefresher, "download"),
        ):
            refresher = OSADLRefresher(store=store)
            refresher.refresh(console=MagicMock())

        mock_reload.assert_called_once()
