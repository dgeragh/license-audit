"""Tests for shared report formatters."""

from __future__ import annotations

from license_audit.core.models import ActionItem, CompatibilityResult, Verdict
from license_audit.reports._format import (
    ActionItemFormatter,
    IncompatiblePairFormatter,
    fenced_code_block,
    license_label,
    markdown_license_cell,
)


class TestLicenseLabel:
    def test_short_value_unchanged(self) -> None:
        assert license_label("BSD-3-Clause") == "BSD-3-Clause"

    def test_collapses_internal_whitespace_and_newlines(self) -> None:
        assert license_label("\n  Proprietary\tLicense") == ("Proprietary License")

    def test_truncates_overlong_value(self) -> None:
        result = license_label("x" * 500, limit=40)
        assert len(result) == 40
        assert result.endswith("…")

    def test_default_limit_is_120(self) -> None:
        # Pins the production default used by every table/notices call site.
        result = license_label("x" * 200)
        assert len(result) == 120
        assert result.endswith("…")


class TestFencedCodeBlock:
    def test_plain_text_uses_three_backticks(self) -> None:
        block = fenced_code_block("just a license\nno fences")
        assert block.startswith("```\n")
        assert not block.startswith("````")
        assert block.endswith("\n```")

    def test_embedded_fence_widens_the_outer_fence(self) -> None:
        # An embedded ``` must not prematurely close the block.
        block = fenced_code_block("LICENSE\n```\nbreakout\n```\nmore")
        assert block.startswith("````\n")
        assert block.endswith("\n````")
        assert "breakout" in block

    def test_outer_fence_longer_than_longest_run(self) -> None:
        block = fenced_code_block("a ```` b")  # 4-backtick run in body
        assert block.startswith("`````\n")  # needs 5


class TestMarkdownLicenseCell:
    def test_escapes_pipes_to_protect_table(self) -> None:
        # A pipe in a declared license would otherwise add phantom columns.
        assert markdown_license_cell("Foo | Bar License") == "Foo \\| Bar License"

    def test_clean_expression_passes_through(self) -> None:
        assert markdown_license_cell("Apache-2.0 OR MIT") == "Apache-2.0 OR MIT"


class TestActionItemFormatterRich:
    def test_warning_uses_yellow(self) -> None:
        item = ActionItem(severity="warning", message="watch out")
        result = ActionItemFormatter.rich(item)
        assert "[yellow]" in result
        assert "watch out" in result

    def test_error_uses_red(self) -> None:
        item = ActionItem(severity="error", message="nope")
        result = ActionItemFormatter.rich(item)
        assert "[red]" in result
        assert "nope" in result

    def test_message_is_escaped(self) -> None:
        """Rich markup characters in the message are escaped to avoid
        accidentally styling user-supplied text."""
        item = ActionItem(severity="warning", message="[x] not markup")
        result = ActionItemFormatter.rich(item)
        # Escaped form prefixes open-brackets with a backslash.
        assert r"\[x]" in result


class TestActionItemFormatterMarkdown:
    def test_warning_label(self) -> None:
        item = ActionItem(severity="warning", message="heads up")
        result = ActionItemFormatter.markdown(item)
        assert result.startswith("- [Warning]")
        assert "heads up" in result

    def test_error_label(self) -> None:
        item = ActionItem(severity="error", message="broken")
        result = ActionItemFormatter.markdown(item)
        assert result.startswith("- [Error]")

    def test_package_prefix_when_set(self) -> None:
        item = ActionItem(severity="error", package="foo", message="x")
        assert "**foo**: x" in ActionItemFormatter.markdown(item)

    def test_no_prefix_when_package_empty(self) -> None:
        item = ActionItem(severity="error", message="x")
        assert "**" not in ActionItemFormatter.markdown(item)


class TestIncompatiblePairFormatter:
    def _pair(self) -> CompatibilityResult:
        return CompatibilityResult(
            inbound="GPL-2.0-only",
            outbound="Apache-2.0",
            verdict=Verdict.INCOMPATIBLE,
        )

    def test_rich(self) -> None:
        result = IncompatiblePairFormatter.rich(self._pair())
        assert "[red]" in result
        assert "GPL-2.0-only" in result
        assert "Apache-2.0" in result

    def test_markdown_row(self) -> None:
        result = IncompatiblePairFormatter.markdown_row(self._pair())
        assert result == "| GPL-2.0-only | Apache-2.0 | incompatible |"
