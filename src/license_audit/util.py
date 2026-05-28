"""Shared utilities for package name handling and metadata reading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from email.message import Message
from email.parser import HeaderParser
from pathlib import Path
from typing import Self


def canonicalize(name: str) -> str:
    """Canonicalize a package name per PEP 503.

    Lowercases and maps hyphens and dots to underscores so names compare
    equal regardless of how they were written on PyPI.
    """
    return name.lower().replace("-", "_").replace(".", "_")


class _DistInfo(ABC):
    """One package's dist-info, backed by either a directory or a zip."""

    @abstractmethod
    def read_text(self, name: str) -> str | None:
        """Read a dist-info-relative path (e.g. ``licenses/LICENSE``).

        Returns None if the file is absent.
        """

    @abstractmethod
    def iter_files(self) -> Iterator[str]:
        """Yield every dist-info-relative path, forward-slashed."""


class _DistInfoDir(_DistInfo):
    """A dist-info directory on the filesystem."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read_text(self, name: str) -> str | None:
        target = self._path / name
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    def iter_files(self) -> Iterator[str]:
        for child in self._path.rglob("*"):
            if child.is_file():
                yield child.relative_to(self._path).as_posix()


class _Source(ABC):
    """A collection of dist-infos addressable by canonical name."""

    @abstractmethod
    def find_dist_info(self, canonical_name: str) -> _DistInfo | None: ...

    @abstractmethod
    def iter_package_names(self) -> Iterator[str]: ...

    @abstractmethod
    def describe(self) -> str:
        """Human-readable label for error messages and logs."""


class _SitePackagesSource(_Source):
    """Reads dist-infos out of an installed site-packages directory."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def find_dist_info(self, canonical_name: str) -> _DistInfo | None:
        for dist_info in self._path.glob("*.dist-info"):
            if self._dist_info_name(dist_info.name) == canonical_name:
                return _DistInfoDir(dist_info)
        return None

    def iter_package_names(self) -> Iterator[str]:
        for dist_info in self._path.glob("*.dist-info"):
            yield self._dist_info_name(dist_info.name)

    def describe(self) -> str:
        return str(self._path)

    @staticmethod
    def _dist_info_name(dir_name: str) -> str:
        stem = dir_name.rsplit(".dist-info", 1)[0]
        return canonicalize(stem.split("-", 1)[0])


class MetadataReader:
    """Reads METADATA and license files for a set of packages.

    The source is bound at construction via :meth:`from_site_packages`.
    """

    LICENSE_FILE_PATTERNS: tuple[str, ...] = (
        "LICENSE",
        "LICENCE",
        "COPYING",
        "NOTICE",
    )

    def __init__(self, source: _Source) -> None:
        self._source = source
        self._parser = HeaderParser()

    @classmethod
    def from_site_packages(cls, path: Path) -> Self:
        """Reader over an installed site-packages directory."""
        return cls(_SitePackagesSource(path))

    def read_metadata(self, package_name: str) -> Message | None:
        """Parsed METADATA for `package_name`, or None if absent."""
        dist_info = self._source.find_dist_info(canonicalize(package_name))
        if dist_info is None:
            return None
        return self._parse_metadata(dist_info)

    def read_license_text(self, package_name: str) -> str | None:
        """Concatenated license-file text for `package_name`.

        PEP 639 ``License-File`` entries are preferred; otherwise
        fall back to ``LICENSE``/``COPYING``/``NOTICE`` filename
        patterns. None when nothing matches.
        """
        dist_info = self._source.find_dist_info(canonicalize(package_name))
        if dist_info is None:
            return None
        texts = self._read_pep639_license_files(dist_info)
        if not texts:
            texts = self._read_common_license_files(dist_info)
        return "\n".join(texts) if texts else None

    def iter_package_names(self) -> Iterable[str]:
        """Canonical names of every package in the source."""
        return self._source.iter_package_names()

    def describe_source(self) -> str:
        """Path or label for the underlying source."""
        return self._source.describe()

    def _parse_metadata(self, dist_info: _DistInfo) -> Message | None:
        text = dist_info.read_text("METADATA")
        if text is None:
            return None
        return self._parser.parsestr(text)

    def _read_pep639_license_files(self, dist_info: _DistInfo) -> list[str]:
        meta = self._parse_metadata(dist_info)
        if meta is None:
            return []
        texts: list[str] = []
        for declared in meta.get_all("License-File") or []:
            # The file lives either at the dist-info root or under licenses/.
            for candidate in (declared, f"licenses/{declared}"):
                content = dist_info.read_text(candidate)
                if content is not None:
                    texts.append(content)
                    break
        return texts

    def _read_common_license_files(self, dist_info: _DistInfo) -> list[str]:
        texts: list[str] = []
        for relative in dist_info.iter_files():
            if not self._is_common_license_path(relative):
                continue
            content = dist_info.read_text(relative)
            if content is not None:
                texts.append(content)
        return texts

    def _is_common_license_path(self, relative: str) -> bool:
        # Match the dist-info root and one level under `licenses/`, no deeper.
        if "/" in relative:
            head, _, base = relative.rpartition("/")
            if head != "licenses":
                return False
        else:
            base = relative
        return any(base.startswith(prefix) for prefix in self.LICENSE_FILE_PATTERNS)
