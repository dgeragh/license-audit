"""Tests pinning the JSON report schema contract."""

import json
import os
from pathlib import Path

from license_audit import __version__
from license_audit.core.models import SCHEMA_VERSION, AnalysisReport
from license_audit.reports.json_report import JsonRenderer

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "reference" / "report-schema.json"
)


class TestSchemaContract:
    def test_checked_in_schema_matches_model(self) -> None:
        schema = AnalysisReport.model_json_schema()
        if os.environ.get("UPDATE_SCHEMA"):
            SCHEMA_PATH.write_text(json.dumps(schema, indent=2) + "\n")
        checked_in = json.loads(SCHEMA_PATH.read_text())
        assert checked_in == schema, (
            "Schema drift: rerun with UPDATE_SCHEMA=1 and review the diff"
        )

    def test_schema_version_is_frozen(self) -> None:
        assert SCHEMA_VERSION == 1
        assert AnalysisReport().schema_version == 1

    def test_tool_version_matches_package(self) -> None:
        assert AnalysisReport().tool_version == __version__

    def test_versions_first_in_json_output(self) -> None:
        data = json.loads(JsonRenderer().render(AnalysisReport()))
        assert list(data)[:2] == ["schema_version", "tool_version"]
