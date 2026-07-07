"""Tests for JSON renderer."""

import json

from license_audit import __version__
from license_audit.core.models import (
    AnalysisReport,
    LicenseCategory,
    LicenseSource,
    PackageLicense,
)
from license_audit.reports.json_report import JsonRenderer


class TestJsonRenderer:
    def test_valid_json(self, sample_report: AnalysisReport) -> None:
        renderer = JsonRenderer()
        result = renderer.render(sample_report)
        data = json.loads(result)
        assert data["schema_version"] == 1
        assert data["tool_version"] == __version__
        assert data["project_name"] == "test-project"
        assert len(data["packages"]) == 2

    def test_empty_report(self) -> None:
        renderer = JsonRenderer()
        result = renderer.render(AnalysisReport())
        data = json.loads(result)
        assert data["packages"] == []

    def test_removed_fields_not_serialized(self) -> None:
        data = json.loads(JsonRenderer().render(AnalysisReport()))
        assert "compatibility_results" not in data
        assert "metadata" not in data

    def test_declared_license_serialized_for_machine_consumers(self) -> None:
        # The machine-readable contract for distinguishing "declared but
        # unrecognized" from "not detected": declared_license is a field;
        # display_license is a property and intentionally NOT serialized.
        report = AnalysisReport(
            project_name="p",
            packages=[
                PackageLicense(
                    name="gpu",
                    version="1.0",
                    license_expression="UNKNOWN",
                    declared_license="Proprietary License",
                    license_source=LicenseSource.METADATA,
                    category=LicenseCategory.UNKNOWN,
                )
            ],
        )
        data = json.loads(JsonRenderer().render(report))
        pkg = data["packages"][0]
        assert pkg["declared_license"] == "Proprietary License"
        assert pkg["license_expression"] == "UNKNOWN"
        assert "display_license" not in pkg

    def test_not_detected_package_has_null_declared_license(self) -> None:
        report = AnalysisReport(
            project_name="p",
            packages=[PackageLicense(name="mystery", version="1.0")],
        )
        data = json.loads(JsonRenderer().render(report))
        assert data["packages"][0]["declared_license"] is None

    def test_category_overridden_serialized(self) -> None:
        # In JSON, category_overridden is the only signal that a category was
        # user-assigned (display_license / "(classified)" are render-only).
        report = AnalysisReport(
            project_name="p",
            packages=[
                PackageLicense(
                    name="gpu",
                    version="1.0",
                    license_expression="UNKNOWN",
                    declared_license="Proprietary License",
                    category=LicenseCategory.PERMISSIVE,
                    category_overridden=True,
                ),
                PackageLicense(name="click", version="8.0", license_expression="MIT"),
            ],
        )
        data = json.loads(JsonRenderer().render(report))
        by_name = {p["name"]: p for p in data["packages"]}
        assert by_name["gpu"]["category_overridden"] is True
        assert by_name["click"]["category_overridden"] is False
