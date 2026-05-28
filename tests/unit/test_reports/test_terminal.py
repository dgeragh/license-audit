"""Tests for TerminalRenderer."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from license_audit.core.models import (
    AnalysisReport,
    CompatibilityResult,
    Verdict,
)
from license_audit.reports.terminal import TerminalRenderer


def _make_console(*, force_terminal: bool = False) -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, force_terminal=force_terminal, width=120)
    return console, buf


class TestTerminalRenderer:
    def test_render_writes_to_console(self, sample_report: AnalysisReport) -> None:
        console, buf = _make_console(force_terminal=True)
        TerminalRenderer(console=console).render(sample_report)
        output = buf.getvalue()
        assert "test-project" in output
        assert "test-pkg" in output

    def test_empty_report(self) -> None:
        console, buf = _make_console(force_terminal=True)
        TerminalRenderer(console=console).render(AnalysisReport(project_name="empty"))
        assert "empty" in buf.getvalue()

    def test_incompatible_pairs_shown(self) -> None:
        console, buf = _make_console()
        report = AnalysisReport(
            project_name="conflict",
            incompatible_pairs=[
                CompatibilityResult(
                    inbound="GPL-2.0-only",
                    outbound="Apache-2.0",
                    verdict=Verdict.INCOMPATIBLE,
                ),
            ],
        )
        TerminalRenderer(console=console).render(report)
        output = buf.getvalue()
        assert "GPL-2.0-only" in output
        assert "Apache-2.0" in output

    def test_no_recommendations(self) -> None:
        console, buf = _make_console()
        report = AnalysisReport(
            project_name="no-compat",
            recommended_licenses=[],
            incompatible_pairs=[
                CompatibilityResult(
                    inbound="GPL-2.0-only",
                    outbound="Apache-2.0",
                    verdict=Verdict.INCOMPATIBLE,
                ),
            ],
        )
        TerminalRenderer(console=console).render(report)
        assert "No compatible outbound license found" in buf.getvalue()

    def test_many_recommendations_truncated(self) -> None:
        console, buf = _make_console()
        report = AnalysisReport(
            project_name="many",
            recommended_licenses=[f"License-{i}" for i in range(15)],
        )
        TerminalRenderer(console=console).render(report)
        assert "and 5 more" in buf.getvalue()

    def test_policy_failed_shown(self) -> None:
        console, buf = _make_console()
        TerminalRenderer(console=console).render(
            AnalysisReport(project_name="fail", policy_passed=False),
        )
        assert "FAILED" in buf.getvalue()

    def test_source_in_header(self) -> None:
        console, buf = _make_console()
        TerminalRenderer(console=console).render(
            AnalysisReport(project_name="p", source="/abs/.venv"),
        )
        assert "Source:" in buf.getvalue()
        assert "/abs/.venv" in buf.getvalue()


class TestCategoryColors:
    def test_every_category_has_a_color(self) -> None:
        from license_audit.core.models import LicenseCategory

        for category in LicenseCategory:
            assert category in TerminalRenderer.CATEGORY_COLORS
            assert TerminalRenderer.CATEGORY_COLORS[category]

    def test_categories_have_distinct_colors(self) -> None:
        colors = list(TerminalRenderer.CATEGORY_COLORS.values())
        assert len(colors) == len(set(colors))

    def test_unknown_is_more_prominent_than_dim(self) -> None:
        from license_audit.core.models import LicenseCategory

        assert TerminalRenderer.CATEGORY_COLORS[LicenseCategory.UNKNOWN] != "dim"


class TestTerminalRendererMarkupSafety:
    """User-controlled text must not be interpreted as Rich markup."""

    def test_ignore_reason_with_brackets_preserved(self) -> None:
        from license_audit.core.models import (
            LicenseCategory,
            LicenseSource,
            PackageLicense,
        )

        console, buf = _make_console()
        report = AnalysisReport(
            project_name="p",
            packages=[
                PackageLicense(
                    name="some_pkg",
                    version="1.0",
                    license_expression="GPL-3.0-only",
                    license_source=LicenseSource.METADATA,
                    category=LicenseCategory.STRONG_COPYLEFT,
                    ignored=True,
                    ignore_reason="Doesn't apply [see issue #123]",
                )
            ],
        )
        TerminalRenderer(console=console).render(report)
        output = buf.getvalue()
        assert "[see issue #123]" in output

    def test_license_expression_with_brackets_preserved(self) -> None:
        from license_audit.core.models import (
            LicenseCategory,
            LicenseSource,
            PackageLicense,
        )

        console, buf = _make_console()
        report = AnalysisReport(
            project_name="p",
            packages=[
                PackageLicense(
                    name="weird_pkg",
                    version="1.0",
                    license_expression="MIT [internal use only]",
                    license_source=LicenseSource.OVERRIDE,
                    category=LicenseCategory.PERMISSIVE,
                )
            ],
        )
        TerminalRenderer(console=console).render(report)
        output = buf.getvalue()
        assert "[internal use only]" in output
