"""Shared utilities for package name handling and metadata reading."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from email.message import Message
from email.parser import HeaderParser
from pathlib import Path
from typing import Self

from packaging.utils import canonicalize_name

# Package metadata and license files are untrusted. Control characters such as
# ANSI escape sequences or a bare carriage return would otherwise reach
# terminals and CI logs verbatim, where they can hide or rewrite output.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def strip_control_chars(text: str) -> str:
    """Remove control characters other than tab and newline."""
    return _CONTROL_CHARS.sub("", text)


def canonicalize(name: str) -> str:
    """Canonicalize a package name per PEP 503.

    Lowercases and collapses runs of hyphens, underscores, and dots to a
    single hyphen, so names compare equal regardless of how they were
    written on PyPI or in dist-info directory names.
    """
    return str(canonicalize_name(name))


class _DistInfo(ABC):
    """One package's dist-info metadata files."""

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
        # A License-File entry is untrusted metadata; keep it inside the
        # dist-info so a crafted wheel can't embed arbitrary files in a report.
        root = self._path.resolve()
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return None
        return strip_control_chars(target.read_text(encoding="utf-8", errors="replace"))

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
        self._entries: list[tuple[str, Path]] | None = None
        self._index: dict[str, Path] = {}

    def find_dist_info(self, canonical_name: str) -> _DistInfo | None:
        self._scan()
        path = self._index.get(canonical_name)
        return _DistInfoDir(path) if path is not None else None

    def iter_package_names(self) -> Iterator[str]:
        for name, _ in self._scan():
            yield name

    def describe(self) -> str:
        return str(self._path)

    def _scan(self) -> list[tuple[str, Path]]:
        # Scanned once: re-globbing and re-sorting the directory on every
        # lookup made an audit quadratic in the number of installed packages.
        if self._entries is None:
            self._entries = [
                (self._dist_info_name(path.name), path)
                for path in self._metadata_dirs()
            ]
            for name, path in self._entries:
                # The first match wins, as it did when lookups scanned in order.
                self._index.setdefault(name, path)
        return self._entries

    def _metadata_dirs(self) -> Iterator[Path]:
        # glob() yields in directory order, which differs between filesystems;
        # sorting keeps report output identical across machines.
        for pattern in ("*.dist-info", "*.egg-info"):
            for path in sorted(self._path.glob(pattern)):
                if path.is_dir():
                    yield path

    @staticmethod
    def _dist_info_name(dir_name: str) -> str:
        stem = strip_control_chars(dir_name).removesuffix(".dist-info")
        stem = stem.removesuffix(".egg-info")
        name = re.split(r"-(?=\d)", stem, maxsplit=1)[0]
        return canonicalize(name)


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
        self._metadata: dict[str, Message | None] = {}

    @classmethod
    def from_site_packages(cls, path: Path) -> Self:
        """Reader over an installed site-packages directory."""
        return cls(_SitePackagesSource(path))

    def read_metadata(self, package_name: str) -> Message | None:
        """Parsed METADATA for `package_name`, or None if absent."""
        canonical = canonicalize(package_name)
        if canonical not in self._metadata:
            dist_info = self._source.find_dist_info(canonical)
            self._metadata[canonical] = (
                None if dist_info is None else self._parse_metadata(dist_info)
            )
        return self._metadata[canonical]

    def is_installed(self, package_name: str) -> bool:
        """True if `package_name` has installed metadata in the source."""
        return self._source.find_dist_info(canonicalize(package_name)) is not None

    def read_license_text(self, package_name: str) -> str | None:
        """Concatenated license-file text for `package_name`.

        PEP 639 ``License-File`` entries are preferred; otherwise
        fall back to ``LICENSE``/``COPYING``/``NOTICE`` filename
        patterns. None when nothing matches.
        """
        dist_info = self._source.find_dist_info(canonicalize(package_name))
        if dist_info is None:
            return None
        texts = self._read_pep639_license_files(
            dist_info, self.read_metadata(package_name)
        )
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
            text = dist_info.read_text("PKG-INFO")
        if text is None:
            return None
        return self._parser.parsestr(text)

    def _read_pep639_license_files(
        self, dist_info: _DistInfo, meta: Message | None
    ) -> list[str]:
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
