"""Renderer protocols.

String renderers return the full output so callers can write it to a file
or echo it.
"""

from __future__ import annotations

from typing import Protocol

from license_audit.core.models import AnalysisReport


class StringRenderer(Protocol):
    """Renders a report and returns it as a string."""

    def render(self, report: AnalysisReport) -> str:
        """Render `report` and return it as a string."""
        ...
