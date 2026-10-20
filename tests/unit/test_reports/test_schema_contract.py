"""Tests pinning the JSON report schema contract."""

import json
import os
from pathlib import Path
from typing import Any

from license_audit import __version__
from license_audit.core.models import SCHEMA_VERSION, AnalysisReport
from license_audit.reports.json_report import JsonRenderer

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "reference" / "report-schema.json"
)


def _canonical(node: Any) -> Any:
    """Erase the spellings that differ between pydantic releases.

    Before 2.10 pydantic wrapped a `$ref` that has sibling keywords in a
    one-item `allOf`, and left out the `type` a `const` implies. Neither
    changes what the schema accepts, so the oldest supported pydantic must
    not read them as drift.
    """
    if isinstance(node, list):
        return [_canonical(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _canonical(value) for key, value in node.items()}
    all_of = node.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1 and set(all_of[0]) == {"$ref"}:
        del node["allOf"]
        node["$ref"] = all_of[0]["$ref"]
    if "const" in node:
        node.pop("type", None)
    return node


class TestSchemaContract:
    def test_checked_in_schema_matches_model(self) -> None:
        schema = AnalysisReport.model_json_schema()
        if os.environ.get("UPDATE_SCHEMA"):
            SCHEMA_PATH.write_text(json.dumps(schema, indent=2) + "\n")
        checked_in = json.loads(SCHEMA_PATH.read_text())
        assert _canonical(checked_in) == _canonical(schema), (
            "Schema drift: rerun with UPDATE_SCHEMA=1 and review the diff"
        )

    def test_canonical_form_ignores_pydantic_spellings(self) -> None:
        old = {"allOf": [{"$ref": "#/$defs/X"}], "default": "a"}
        new = {"$ref": "#/$defs/X", "default": "a"}
        assert _canonical(old) == _canonical(new)
        assert _canonical({"const": 2}) == _canonical({"const": 2, "type": "integer"})
        assert _canonical({"type": "integer"}) != _canonical({"type": "string"})

    def test_schema_version_is_frozen(self) -> None:
        assert SCHEMA_VERSION == 2
        assert AnalysisReport().schema_version == 2

    def test_tool_version_matches_package(self) -> None:
        assert AnalysisReport().tool_version == __version__

    def test_versions_first_in_json_output(self) -> None:
        data = json.loads(JsonRenderer().render(AnalysisReport()))
        assert list(data)[:2] == ["schema_version", "tool_version"]
