"""Tests for license detection."""

from __future__ import annotations

from email.message import Message
from pathlib import Path

from license_audit.core.models import LicenseSource
from license_audit.licenses.detection import (
    DetectionResult,
    _detect_from_metadata,
    _try_classifiers,
    _try_license_field,
    _try_pep639,
    detect_license,
)
from license_audit.util import MetadataReader


def _make_metadata(**headers: str | list[str]) -> Message:
    """Create a fake email.message.Message with the given headers."""
    msg = Message()
    for key, val in headers.items():
        key = key.replace("_", "-")
        if isinstance(val, list):
            for v in val:
                msg[key] = v
        else:
            msg[key] = val
    return msg


def _write_dist_info(
    site_packages: Path,
    name: str,
    version: str,
    metadata_extra: str = "",
) -> None:
    dist_info = site_packages / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata_extra}"
    )


class TestDetectLicense:
    def test_override_takes_precedence(self, tmp_path: Path) -> None:
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license(
            "mypkg",
            reader,
            overrides={"mypkg": "Apache-2.0"},
        )
        assert result.expression == "Apache-2.0"
        assert result.source == LicenseSource.OVERRIDE
        assert result.declared_license is None

    def test_override_key_matches_canonical_name(self, tmp_path: Path) -> None:
        # Overrides are written PyPI-style (hyphens), but the lookup name is
        # canonicalized, so the two must still match.
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license(
            "my_internal_package",
            reader,
            overrides={"my-internal-package": "MIT"},
        )
        assert result.expression == "MIT"
        assert result.source == LicenseSource.OVERRIDE

    def test_override_value_normalized(self, tmp_path: Path) -> None:
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license("mypkg", reader, overrides={"mypkg": "apache 2.0"})
        assert result.expression == "Apache-2.0"
        assert result.source == LicenseSource.OVERRIDE
        assert result.declared_license is None

    def test_unrecognized_override_preserved_as_declared(self, tmp_path: Path) -> None:
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license("mypkg", reader, overrides={"mypkg": "Custom EULA"})
        assert result.expression == "UNKNOWN"
        assert result.source == LicenseSource.OVERRIDE
        assert result.declared_license == "Custom EULA"

    def test_reads_from_dist_info(self, tmp_path: Path) -> None:
        _write_dist_info(
            tmp_path,
            "tools",
            "1.0.0",
            metadata_extra="License-Expression: MIT\n",
        )
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license("tools", reader)
        assert result.expression == "MIT"
        assert result.source == LicenseSource.PEP639

    def test_nonexistent_package(self, tmp_path: Path) -> None:
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license("nonexistent", reader)
        assert result.expression == "UNKNOWN"
        assert result.source == LicenseSource.UNKNOWN
        assert result.declared_license is None

    def test_unrecognized_license_preserves_declared_string(
        self, tmp_path: Path
    ) -> None:
        _write_dist_info(
            tmp_path,
            "gpu",
            "1.0.0",
            metadata_extra="License: Proprietary License\n",
        )
        reader = MetadataReader.from_site_packages(tmp_path)
        result = detect_license("gpu", reader)
        assert result.expression == "UNKNOWN"
        assert result.declared_license == "Proprietary License"
        assert result.source == LicenseSource.METADATA


class TestTryPep639:
    def test_valid_expression(self) -> None:
        meta = _make_metadata(License_Expression="MIT")
        result = _try_pep639(meta)
        assert result is not None
        assert result.expression == "MIT"
        assert result.source == LicenseSource.PEP639
        assert result.declared_license is None

    def test_unknown_value_skipped(self) -> None:
        meta = _make_metadata(License_Expression="UNKNOWN")
        assert _try_pep639(meta) is None

    def test_empty_value_skipped(self) -> None:
        meta = _make_metadata(License_Expression="")
        assert _try_pep639(meta) is None

    def test_missing_field(self) -> None:
        meta = _make_metadata()
        assert _try_pep639(meta) is None

    def test_unrecognized_expression_preserves_raw_string(self) -> None:
        meta = _make_metadata(License_Expression="Proprietary License")
        result = _try_pep639(meta)
        assert result is not None
        assert result.expression == "UNKNOWN"
        assert result.declared_license == "Proprietary License"
        assert result.source == LicenseSource.PEP639


class TestTryLicenseField:
    def test_valid_license(self) -> None:
        meta = _make_metadata(License="MIT License")
        result = _try_license_field(meta)
        assert result is not None
        assert result.source == LicenseSource.METADATA
        assert result.declared_license is None

    def test_unknown_skipped(self) -> None:
        meta = _make_metadata(License="UNKNOWN")
        assert _try_license_field(meta) is None

    def test_none_skipped(self) -> None:
        meta = _make_metadata(License="NONE")
        assert _try_license_field(meta) is None

    def test_empty_skipped(self) -> None:
        meta = _make_metadata(License="")
        assert _try_license_field(meta) is None

    def test_unrecognized_license_preserves_raw_string(self) -> None:
        meta = _make_metadata(License="Weird Custom Terms v3")
        result = _try_license_field(meta)
        assert result is not None
        assert result.expression == "UNKNOWN"
        assert result.declared_license == "Weird Custom Terms v3"
        assert result.source == LicenseSource.METADATA


class TestTryClassifiers:
    def test_single_classifier(self) -> None:
        meta = _make_metadata(Classifier=["License :: OSI Approved :: MIT License"])
        result = _try_classifiers(meta)
        assert result is not None
        assert result.expression == "MIT"
        assert result.source == LicenseSource.CLASSIFIER

    def test_multiple_classifiers_produce_or_expression(self) -> None:
        meta = _make_metadata(
            Classifier=[
                "License :: OSI Approved :: MIT License",
                "License :: OSI Approved :: Apache Software License",
            ]
        )
        result = _try_classifiers(meta)
        assert result is not None
        assert "OR" in result.expression
        assert result.source == LicenseSource.CLASSIFIER

    def test_no_license_classifiers(self) -> None:
        meta = _make_metadata(Classifier=["Programming Language :: Python :: 3"])
        assert _try_classifiers(meta) is None

    def test_unrecognized_license_classifier_preserves_declared(self) -> None:
        meta = _make_metadata(Classifier=["License :: Other/Proprietary License"])
        result = _try_classifiers(meta)
        assert result is not None
        assert result.expression == "UNKNOWN"
        assert result.source == LicenseSource.CLASSIFIER
        assert result.declared_license == "Other/Proprietary License"

    def test_multiple_unrecognized_classifiers_joined(self) -> None:
        meta = _make_metadata(
            Classifier=[
                "License :: Other/Proprietary License",
                "License :: Free For Educational Use",
            ]
        )
        result = _try_classifiers(meta)
        assert result is not None
        assert result.declared_license == (
            "Other/Proprietary License; Free For Educational Use"
        )

    def test_bare_license_classifier_is_not_declared(self) -> None:
        # A malformed bare "License ::" has no segment, so it must not surface
        # an empty declared license or a leading "; " join artifact.
        meta = _make_metadata(
            Classifier=["License ::", "License :: Other/Proprietary License"]
        )
        result = _try_classifiers(meta)
        assert result is not None
        assert result.declared_license == "Other/Proprietary License"

    def test_only_bare_license_classifier_returns_none(self) -> None:
        meta = _make_metadata(Classifier=["License ::"])
        assert _try_classifiers(meta) is None


class TestDetectFromMetadata:
    def test_pep639_preferred_over_license_field(self) -> None:
        meta = _make_metadata(
            License_Expression="Apache-2.0",
            License="MIT License",
        )
        result = _detect_from_metadata(meta)
        assert result.expression == "Apache-2.0"
        assert result.source == LicenseSource.PEP639

    def test_falls_back_to_license_field(self) -> None:
        meta = _make_metadata(License="MIT License")
        result = _detect_from_metadata(meta)
        assert result.source == LicenseSource.METADATA

    def test_falls_back_to_classifiers(self) -> None:
        meta = _make_metadata(Classifier=["License :: OSI Approved :: MIT License"])
        result = _detect_from_metadata(meta)
        assert result.expression == "MIT"
        assert result.source == LicenseSource.CLASSIFIER

    def test_returns_unknown_when_nothing_found(self) -> None:
        meta = _make_metadata()
        result = _detect_from_metadata(meta)
        assert result.expression == "UNKNOWN"
        assert result.source == LicenseSource.UNKNOWN
        assert result.declared_license is None

    def test_recognized_classifier_wins_over_unrecognized_license_field(self) -> None:
        # A recognized SPDX result anywhere beats a declared-but-unrecognized one.
        meta = _make_metadata(
            License="Some Bespoke License",
            Classifier=["License :: OSI Approved :: MIT License"],
        )
        result = _detect_from_metadata(meta)
        assert result.expression == "MIT"
        assert result.declared_license is None

    def test_declared_unrecognized_surfaced_when_no_spdx_found(self) -> None:
        meta = _make_metadata(License="Some Bespoke License")
        result = _detect_from_metadata(meta)
        assert result.expression == "UNKNOWN"
        assert result.declared_license == "Some Bespoke License"

    def test_pep639_declared_string_preferred_over_classifier_declared(self) -> None:
        meta = _make_metadata(
            License_Expression="Custom GPU EULA",
            Classifier=["License :: Other/Proprietary License"],
        )
        result = _detect_from_metadata(meta)
        assert result.expression == "UNKNOWN"
        assert result.declared_license == "Custom GPU EULA"
        assert result.source == LicenseSource.PEP639


class TestDetectionResult:
    def test_recognized_property(self) -> None:
        assert DetectionResult("MIT", LicenseSource.PEP639).recognized
        assert not DetectionResult("UNKNOWN", LicenseSource.UNKNOWN).recognized
