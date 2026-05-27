"""Base types for dependency source parsers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PackageSpec:
    """A package name and optional version constraint from a dependency source."""

    name: str
    version_constraint: str = ""
    source_url: str = ""
    extras: frozenset[str] = frozenset()
    index_url: str = ""


class Source(Protocol):
    """Protocol for dependency source parsers.

    A Source reads a dependency specifier file and returns a flat list
    of package specs. It does NOT detect licenses or build dependency trees.
    """

    def parse(self) -> list[PackageSpec]:
        """Parse the source and return package specifications."""
        ...
