"""Tests for markdown renderer."""

from license_audit.core.models import (
    AnalysisReport,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
)
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


def _unrecognized_pkg(
    *,
    declared_license: str | None,
    license_text: str | None,
    name: str = "proprietary-package",
) -> PackageLicense:
    return PackageLicense(
        name=name,
        version="12.0.0",
        license_expression="UNKNOWN",
        declared_license=declared_license,
        license_source=LicenseSource.METADATA,
        category=LicenseCategory.UNKNOWN,
        license_text=license_text,
    )


class TestLicensesRequiringReview:
    def test_declared_license_appears_in_dependency_table(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license="Proprietary License", license_text=None
                )
            ],
        )
        result = MarkdownRenderer().render(report)
        # Pin the actual table row (not just "somewhere downstream", which the
        # review section would also satisfy): the cell shows the declared string
        # instead of bare UNKNOWN.
        row = next(
            line
            for line in result.splitlines()
            if line.startswith("| proprietary-package")
        )
        assert "Proprietary License" in row
        assert "UNKNOWN" not in row

    def test_multiline_declared_license_collapses_to_one_table_row(self) -> None:
        # Some packages stuff a whole body into the License field; the table
        # cell must stay single-line or it would break the markdown table.
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license="Line one\nLine two\n\nLine three",
                    license_text=None,
                )
            ],
        )
        result = MarkdownRenderer().render(report)
        row = next(
            line
            for line in result.splitlines()
            if line.startswith("| proprietary-package")
        )
        assert "\n" not in row
        assert "Line one Line two Line three" in row

    def test_section_includes_license_text_for_verification(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license="Proprietary License",
                    license_text="SOFTWARE LICENSE AGREEMENT\nSection 1...",
                )
            ],
        )
        result = MarkdownRenderer().render(report)
        assert "## Licenses Requiring Review" in result
        assert "### proprietary-package 12.0.0" in result
        assert "**Declared license:** Proprietary License" in result
        assert "SOFTWARE LICENSE AGREEMENT" in result

    def test_section_notes_missing_text(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[_unrecognized_pkg(declared_license=None, license_text=None)],
        )
        result = MarkdownRenderer().render(report)
        assert "## Licenses Requiring Review" in result
        assert "License text not available" in result

    def test_undetected_package_labeled_not_detected(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license=None,
                    license_text="Some bundled LICENSE file contents",
                    name="mystery",
                )
            ],
        )
        result = MarkdownRenderer().render(report)
        assert "### mystery 12.0.0" in result
        assert "**License:** not detected" in result
        assert "Some bundled LICENSE file contents" in result

    def test_no_section_when_all_recognized(
        self, sample_report: AnalysisReport
    ) -> None:
        result = MarkdownRenderer().render(sample_report)
        assert "## Licenses Requiring Review" not in result

    def test_classified_package_annotated_and_excluded_from_review(self) -> None:
        pkg = PackageLicense(
            name="proprietary-package",
            version="12.0.0",
            license_expression="UNKNOWN",
            declared_license="Proprietary License",
            license_source=LicenseSource.METADATA,
            category=LicenseCategory.PERMISSIVE,
            category_overridden=True,
        )
        report = AnalysisReport(project_name="p", packages=[pkg])
        result = MarkdownRenderer().render(report)
        row = next(
            line
            for line in result.splitlines()
            if line.startswith("| proprietary-package")
        )
        assert "Proprietary License" in row
        assert "permissive (classified)" in row
        assert "## Licenses Requiring Review" not in result

    def test_ignored_unknown_excluded_from_review(self) -> None:
        pkg = _unrecognized_pkg(
            declared_license="Proprietary License",
            license_text="text",
        )
        pkg.ignored = True
        report = AnalysisReport(project_name="p", packages=[pkg])
        result = MarkdownRenderer().render(report)
        assert "## Licenses Requiring Review" not in result

    def test_pipe_in_declared_license_does_not_break_table(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license="Custom | Weird License", license_text=None
                )
            ],
        )
        result = MarkdownRenderer().render(report)
        table_row = next(
            line
            for line in result.splitlines()
            if line.startswith("| proprietary-package")
        )
        # The pipe is escaped, so it no longer acts as a column delimiter:
        # stripping the escaped form leaves exactly the 6-column structure.
        assert "Custom \\| Weird License" in table_row
        assert table_row.replace("\\|", "").count("|") == 7  # 6 columns

    def test_embedded_fence_in_license_text_does_not_break_block(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license="Evil EULA",
                    license_text="TERMS\n```\nembedded fence\n```\nmore terms",
                )
            ],
        )
        review = (
            MarkdownRenderer().render(report).split("## Licenses Requiring Review")[1]
        )
        assert "````" in review  # widened fence
        assert "embedded fence" in review
        assert "more terms" in review

    def test_review_falls_back_to_declared_string_as_content(self) -> None:
        # Some packages put the whole license body in metadata, no LICENSE file.
        report = AnalysisReport(
            project_name="p",
            packages=[
                _unrecognized_pkg(
                    declared_license="WHOLE LICENSE BODY embedded in metadata field",
                    license_text=None,
                )
            ],
        )
        result = MarkdownRenderer().render(report)
        review_section = result.split("## Licenses Requiring Review")[1]
        assert "WHOLE LICENSE BODY embedded in metadata field" in review_section
        assert "License text not available" not in review_section
