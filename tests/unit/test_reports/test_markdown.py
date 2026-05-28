"""Tests for markdown renderer."""

from license_audit.core.models import AnalysisReport
from license_audit.reports.markdown import MarkdownRenderer


class TestMarkdownRenderer:
    def test_contains_sections(self, sample_report: AnalysisReport) -> None:
        renderer = MarkdownRenderer()
        result = renderer.render(sample_report)
        assert "# License Compliance Report" in result
        assert "## Summary" in result
        assert "## Dependency Licenses" in result
        assert "## Recommended Licenses" in result
        assert "test-project" in result

    def test_dependency_table(self, sample_report: AnalysisReport) -> None:
        renderer = MarkdownRenderer()
        result = renderer.render(sample_report)
        assert "test-pkg" in result
        assert "gpl-pkg" in result
        assert "MIT" in result

    def test_empty_report(self) -> None:
        renderer = MarkdownRenderer()
        result = renderer.render(AnalysisReport())
        assert "# License Compliance Report" in result

    def test_incompatible_pairs_section(self) -> None:
        from license_audit.core.models import CompatibilityResult, Verdict

        report = AnalysisReport(
            project_name="conflict-project",
            incompatible_pairs=[
                CompatibilityResult(
                    inbound="GPL-2.0-only",
                    outbound="Apache-2.0",
                    verdict=Verdict.INCOMPATIBLE,
                )
            ],
        )
        renderer = MarkdownRenderer()
        result = renderer.render(report)
        assert "Incompatible license pairs detected" in result
        assert "GPL-2.0-only" in result

    def test_no_compatible_licenses(self) -> None:
        from license_audit.core.models import CompatibilityResult, Verdict

        report = AnalysisReport(
            project_name="no-compat",
            recommended_licenses=[],
            incompatible_pairs=[
                CompatibilityResult(
                    inbound="GPL-2.0-only",
                    outbound="Apache-2.0",
                    verdict=Verdict.INCOMPATIBLE,
                )
            ],
        )
        renderer = MarkdownRenderer()
        result = renderer.render(report)
        assert "No compatible outbound license found" in result
        assert "override" in result.lower() or "replacing" in result.lower()

    def test_action_items_section(self) -> None:
        from license_audit.core.models import ActionItem

        report = AnalysisReport(
            project_name="action-project",
            action_items=[
                ActionItem(
                    severity="error", package="bad-pkg", message="Denied license."
                ),
                ActionItem(
                    severity="warning", package="warn-pkg", message="Unknown license."
                ),
            ],
        )
        renderer = MarkdownRenderer()
        result = renderer.render(report)
        assert "Action Items" in result
        assert "bad-pkg" in result
        assert "warn-pkg" in result

    def test_many_recommended_licenses(self) -> None:
        report = AnalysisReport(
            project_name="many-lic",
            recommended_licenses=[f"License-{i}" for i in range(15)],
        )
        renderer = MarkdownRenderer()
        result = renderer.render(report)
        assert "...and 5 more" in result

    def test_source_in_header(self) -> None:
        report = AnalysisReport(project_name="p", source="/abs/path/.venv")
        result = MarkdownRenderer().render(report)
        assert "Source: /abs/path/.venv" in result

    def test_no_source_line_when_empty(self) -> None:
        result = MarkdownRenderer().render(AnalysisReport(project_name="p"))
        assert "Source:" not in result
