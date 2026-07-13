"""Tests for SpdxNormalizer."""

from __future__ import annotations

from license_expression import AND, OR

from license_audit.licenses.spdx import SpdxNormalizer


class TestNormalize:
    def test_valid_spdx(self) -> None:
        assert SpdxNormalizer().normalize("MIT") == "MIT"

    def test_apache_alias(self) -> None:
        assert SpdxNormalizer().normalize("Apache Software License") == "Apache-2.0"

    def test_bsd_alias(self) -> None:
        assert SpdxNormalizer().normalize("BSD License") == "BSD-3-Clause"

    def test_case_insensitive(self) -> None:
        n = SpdxNormalizer()
        assert n.normalize("mit license") == "MIT"
        assert n.normalize("MIT LICENSE") == "MIT"

    def test_unknown(self) -> None:
        n = SpdxNormalizer()
        assert n.normalize("UNKNOWN") == "UNKNOWN"
        assert n.normalize("") == "UNKNOWN"
        assert n.normalize("   ") == "UNKNOWN"

    def test_compound_expression(self) -> None:
        result = SpdxNormalizer().normalize("MIT OR Apache-2.0")
        assert "MIT" in result
        assert "Apache-2.0" in result

    def test_gpl_aliases(self) -> None:
        n = SpdxNormalizer()
        assert n.normalize("GPLv3") == "GPL-3.0-only"
        assert n.normalize("GNU GPL v2") == "GPL-2.0-only"

    def test_deprecated_spdx_normalized(self) -> None:
        n = SpdxNormalizer()
        assert n.normalize("GPL-2.0") == "GPL-2.0-only"
        assert n.normalize("LGPL-3.0") == "LGPL-3.0-only"
        assert n.normalize("AGPL-3.0") == "AGPL-3.0-only"

    def test_nonspdx_string_returns_unknown(self) -> None:
        n = SpdxNormalizer()
        assert n.normalize("Dual License") == "UNKNOWN"
        assert n.normalize("Custom License v2") == "UNKNOWN"

    def test_none_value(self) -> None:
        assert SpdxNormalizer().normalize("NONE") == "UNKNOWN"

    def test_spdx_id_outside_matrix(self) -> None:
        n = SpdxNormalizer()
        assert n.normalize("CNRI-Python") == "CNRI-Python"
        assert n.normalize("Apache-2.0 AND CNRI-Python") == "Apache-2.0 AND CNRI-Python"

    def test_compound_case_canonicalized(self) -> None:
        assert SpdxNormalizer().normalize("mit and apache-2.0") == "MIT AND Apache-2.0"

    def test_deprecated_id_inside_compound(self) -> None:
        assert SpdxNormalizer().normalize("GPL-2.0+ AND MIT") == (
            "GPL-2.0-or-later AND MIT"
        )

    def test_matrix_id_outside_spdx_list(self) -> None:
        assert SpdxNormalizer().normalize("MPL-2.0-no-copyleft-exception") == (
            "MPL-2.0-no-copyleft-exception"
        )

    def test_with_exception(self) -> None:
        assert SpdxNormalizer().normalize("Apache-2.0 WITH LLVM-exception") == (
            "Apache-2.0 WITH LLVM-exception"
        )

    def test_truncated_expression_returns_unknown(self) -> None:
        assert SpdxNormalizer().normalize("MIT AND") == "UNKNOWN"

    def test_with_clause_rejected_by_validate_returns_unknown(self) -> None:
        assert (
            SpdxNormalizer().normalize(
                "MPL-2.0-no-copyleft-exception WITH LLVM-exception",
            )
            == "UNKNOWN"
        )


class TestNormalizeClassifier:
    def test_mit(self) -> None:
        result = SpdxNormalizer().normalize_classifier(
            "License :: OSI Approved :: MIT License",
        )
        assert result == "MIT"

    def test_apache(self) -> None:
        result = SpdxNormalizer().normalize_classifier(
            "License :: OSI Approved :: Apache Software License",
        )
        assert result == "Apache-2.0"

    def test_unknown_classifier(self) -> None:
        result = SpdxNormalizer().normalize_classifier("License :: Something Unknown")
        assert result is None


class TestParseExpression:
    def test_simple(self) -> None:
        assert SpdxNormalizer().parse_expression("MIT") is not None

    def test_compound_or(self) -> None:
        parsed = SpdxNormalizer().parse_expression("MIT OR Apache-2.0")
        assert isinstance(parsed, OR)

    def test_compound_and(self) -> None:
        parsed = SpdxNormalizer().parse_expression("MIT AND Apache-2.0")
        assert isinstance(parsed, AND)

    def test_invalid(self) -> None:
        assert SpdxNormalizer().parse_expression("not a valid expression!!!") is None


class TestGetSimpleLicenses:
    def test_single(self) -> None:
        assert SpdxNormalizer().get_simple_licenses("MIT") == ["MIT"]

    def test_or_expression(self) -> None:
        result = SpdxNormalizer().get_simple_licenses("MIT OR Apache-2.0")
        assert "MIT" in result
        assert "Apache-2.0" in result

    def test_unparseable(self) -> None:
        assert SpdxNormalizer().get_simple_licenses("garbage!!!") == ["garbage!!!"]

    def test_with_clause_kept_intact(self) -> None:
        result = SpdxNormalizer().get_simple_licenses(
            "MIT AND Apache-2.0 WITH LLVM-exception",
        )
        assert "MIT" in result
        assert "Apache-2.0 WITH LLVM-exception" in result

    def test_deprecated_id_promoted(self) -> None:
        result = SpdxNormalizer().get_simple_licenses("GPL-2.0 AND MIT")
        assert set(result) == {"GPL-2.0-only", "MIT"}


class TestKnownSpdxIds:
    def test_contains_matrix_and_aliases(self) -> None:
        ids = SpdxNormalizer().known_spdx_ids()
        assert "MIT" in ids
        assert "GPL-3.0-only" in ids
        # Target of an alias that may not be in the matrix:
        assert "CC0-1.0" in ids
