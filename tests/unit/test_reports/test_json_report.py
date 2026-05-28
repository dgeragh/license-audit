"""Tests for JSON renderer."""

import json

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
        assert data["project_name"] == "test-project"
        assert len(data["packages"]) == 2

    def test_empty_report(self) -> None:
        renderer = JsonRenderer()
        result = renderer.render(AnalysisReport())
        data = json.loads(result)
        assert data["packages"] == []

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
