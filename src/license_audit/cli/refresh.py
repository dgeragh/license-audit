"""The `refresh` CLI command. Updates the cached OSADL data."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import click
from rich.console import Console

from license_audit._data import OSADLDataStore


class OSADLRefresher:
    """Downloads the latest OSADL matrix and copyleft data into the user cache."""

    MATRIX_URL = "https://www.osadl.org/fileadmin/checklists/matrix.json"
    COPYLEFT_URL = "https://www.osadl.org/fileadmin/checklists/copyleft.json"
    MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
    TIMEOUT_SECONDS = 30

    def __init__(self, store: OSADLDataStore | None = None) -> None:
        self._store = store or OSADLDataStore()

    def refresh(self, console: Console) -> None:
        """Download both OSADL files and reload the data store."""
        data_path = self._store.cache_dir()
        data_path.mkdir(parents=True, exist_ok=True)

        console.print("Downloading OSADL compatibility matrix...")
        self.download(self.MATRIX_URL, data_path / self._store.MATRIX_FILE)
        console.print("[green]\\[/][/green] matrix.json updated")

        console.print("Downloading OSADL copyleft data...")
        self.download(self.COPYLEFT_URL, data_path / self._store.COPYLEFT_FILE)
        console.print("[green]\\[/][/green] copyleft.json updated")

        self._store.reload()

        console.print(f"\nData saved to {data_path}")
        console.print("[bold green]OSADL data refreshed successfully.[/bold green]")

    def download(self, url: str, dest: Path) -> None:
        """Download `url` to `dest`, rejecting oversized or invalid payloads."""
        with urlopen(url, timeout=self.TIMEOUT_SECONDS) as resp:  # noqa: S310
            data = resp.read(self.MAX_RESPONSE_BYTES + 1)
        if len(data) > self.MAX_RESPONSE_BYTES:
            msg = f"Response from {url} exceeds {self.MAX_RESPONSE_BYTES} bytes"
            raise RuntimeError(msg)
        # Parse before writing so malformed data never lands in the cache.
        json.loads(data)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)


@click.command("refresh")
def refresh_cmd() -> None:
    """Download the latest OSADL compatibility data."""
    OSADLRefresher().refresh(Console())
