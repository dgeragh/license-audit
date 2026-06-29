"""Tests for util module - license text extraction from site-packages."""

from __future__ import annotations

from pathlib import Path

from license_audit.util import MetadataReader, canonicalize


def get_license_text(package_name: str, site_packages: Path) -> str | None:
    return MetadataReader.from_site_packages(site_packages).read_license_text(
        package_name
    )


def _make_dist_info(
    site_packages: Path,
    name: str,
    version: str,
    metadata_extra: str = "",
    license_files: dict[str, str] | None = None,
    license_subdir_files: dict[str, str] | None = None,
) -> Path:
    """Create a minimal dist-info directory for testing."""
    dist_info = site_packages / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    metadata = (
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata_extra}"
    )
    (dist_info / "METADATA").write_text(metadata)

    if license_files:
        for filename, content in license_files.items():
            (dist_info / filename).write_text(content)

    if license_subdir_files:
        licenses_dir = dist_info / "licenses"
        licenses_dir.mkdir()
        for filename, content in license_subdir_files.items():
            (licenses_dir / filename).write_text(content)

    return dist_info


class TestCanonicalize:
    def test_lowercases_and_replaces_separators(self) -> None:
        assert canonicalize("My-Cool.Pkg") == "my_cool_pkg"


class TestGetLicenseText:
    def test_no_matching_package(self, tmp_path: Path) -> None:
        _make_dist_info(tmp_path, "other_pkg", "1.0.0")
        assert get_license_text("nonexistent", tmp_path) is None

    def test_no_license_files_at_all(self, tmp_path: Path) -> None:
        _make_dist_info(tmp_path, "bare_pkg", "1.0.0")
        assert get_license_text("bare_pkg", tmp_path) is None

    def test_pep639_license_file_in_root(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "root_lic",
            "1.0.0",
            metadata_extra="License-File: LICENSE\n",
            license_files={"LICENSE": "MIT License\nCopyright 2024"},
        )
        result = get_license_text("root_lic", tmp_path)
        assert result is not None
        assert "MIT License" in result
        assert "Copyright 2024" in result

    def test_pep639_license_file_in_licenses_subdir(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "subdir_lic",
            "2.0.0",
            metadata_extra="License-File: LICENSE.txt\n",
            license_subdir_files={"LICENSE.txt": "BSD 2-Clause License"},
        )
        result = get_license_text("subdir_lic", tmp_path)
        assert result is not None
        assert "BSD 2-Clause License" in result

    def test_pep639_prefers_root_over_subdir(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "both_lic",
            "1.0.0",
            metadata_extra="License-File: LICENSE\n",
            license_files={"LICENSE": "Root license text"},
            license_subdir_files={"LICENSE": "Subdir license text"},
        )
        result = get_license_text("both_lic", tmp_path)
        assert result is not None
        assert "Root license text" in result

    def test_pep639_multiple_license_files(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "multi_lic",
            "1.0.0",
            metadata_extra="License-File: LICENSE\nLicense-File: NOTICE\n",
            license_subdir_files={
                "LICENSE": "Apache License 2.0",
                "NOTICE": "Additional notices here",
            },
        )
        result = get_license_text("multi_lic", tmp_path)
        assert result is not None
        assert "Apache License 2.0" in result
        assert "Additional notices here" in result

    def test_pep639_missing_declared_file_skipped(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "missing_lic",
            "1.0.0",
            metadata_extra="License-File: LICENSE\nLicense-File: NOTICE\n",
            license_subdir_files={"LICENSE": "Only this one exists"},
        )
        result = get_license_text("missing_lic", tmp_path)
        assert result is not None
        assert "Only this one exists" in result

    def test_fallback_common_license_in_root(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "fallback_root",
            "1.0.0",
            license_files={"LICENSE": "Fallback root license"},
        )
        result = get_license_text("fallback_root", tmp_path)
        assert result is not None
        assert "Fallback root license" in result

    def test_fallback_common_license_in_subdir(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "fallback_sub",
            "1.0.0",
            license_subdir_files={"COPYING": "GPL v3 text"},
        )
        result = get_license_text("fallback_sub", tmp_path)
        assert result is not None
        assert "GPL v3 text" in result

    def test_fallback_licence_spelling(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "british_pkg",
            "1.0.0",
            license_files={"LICENCE": "British spelling license"},
        )
        result = get_license_text("british_pkg", tmp_path)
        assert result is not None
        assert "British spelling license" in result

    def test_fallback_notice_file(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "notice_pkg",
            "1.0.0",
            license_subdir_files={"NOTICE": "Third party notice content"},
        )
        result = get_license_text("notice_pkg", tmp_path)
        assert result is not None
        assert "Third party notice content" in result

    def test_name_canonicalization(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "my_cool_pkg",
            "1.0.0",
            license_files={"LICENSE": "Canonical license"},
        )
        assert get_license_text("my-cool-pkg", tmp_path) is not None
        assert get_license_text("my.cool.pkg", tmp_path) is not None
        assert get_license_text("My-Cool-Pkg", tmp_path) is not None

    def test_pep639_takes_precedence_over_fallback(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "precedence_pkg",
            "1.0.0",
            metadata_extra="License-File: LICENSE.md\n",
            license_files={
                "LICENSE.md": "PEP 639 license",
                "COPYING": "Fallback license",
            },
        )
        result = get_license_text("precedence_pkg", tmp_path)
        assert result is not None
        assert "PEP 639 license" in result
        assert "Fallback license" not in result

    def test_no_metadata_file(self, tmp_path: Path) -> None:
        dist_info = tmp_path / "nometadata-1.0.0.dist-info"
        dist_info.mkdir()
        (dist_info / "LICENSE").write_text("License without metadata")
        # No METADATA file - PEP 639 path returns empty, fallback finds it
        result = get_license_text("nometadata", tmp_path)
        assert result is not None
        assert "License without metadata" in result

    def test_empty_site_packages(self, tmp_path: Path) -> None:
        assert get_license_text("anything", tmp_path) is None


class TestMetadataReader:
    def test_read_metadata_returns_parsed_headers(self, tmp_path: Path) -> None:
        _make_dist_info(tmp_path, "mypkg", "1.2.3")
        reader = MetadataReader.from_site_packages(tmp_path)
        meta = reader.read_metadata("mypkg")
        assert meta is not None
        assert meta.get("Name") == "mypkg"
        assert meta.get("Version") == "1.2.3"

    def test_read_metadata_missing_package(self, tmp_path: Path) -> None:
        assert MetadataReader.from_site_packages(tmp_path).read_metadata("nope") is None

    def test_read_metadata_canonicalizes_name(self, tmp_path: Path) -> None:
        _make_dist_info(tmp_path, "my_cool_pkg", "1.0.0")
        reader = MetadataReader.from_site_packages(tmp_path)
        assert reader.read_metadata("my-cool-pkg") is not None
        assert reader.read_metadata("My.Cool.Pkg") is not None

    def test_read_license_text_delegates(self, tmp_path: Path) -> None:
        _make_dist_info(
            tmp_path,
            "lic_pkg",
            "1.0.0",
            license_files={"LICENSE": "Text body"},
        )
        reader = MetadataReader.from_site_packages(tmp_path)
        assert reader.read_license_text("lic_pkg") == "Text body"

    def test_iter_package_names_yields_canonical(self, tmp_path: Path) -> None:
        _make_dist_info(tmp_path, "first_pkg", "1.0.0")
        _make_dist_info(tmp_path, "second_pkg", "2.0.0")
        reader = MetadataReader.from_site_packages(tmp_path)
        assert sorted(reader.iter_package_names()) == ["first_pkg", "second_pkg"]

    def test_describe_source_returns_path(self, tmp_path: Path) -> None:
        reader = MetadataReader.from_site_packages(tmp_path)
        assert reader.describe_source() == str(tmp_path)

    def test_hyphenated_dist_info_name_resolved(self, tmp_path: Path) -> None:
        # Some installers leave hyphens in the dist-info name; it must resolve to
        # the full canonical name, not get truncated at the first hyphen.
        _make_dist_info(tmp_path, "ruamel-yaml-clib", "0.2.7")
        reader = MetadataReader.from_site_packages(tmp_path)
        assert "ruamel_yaml_clib" in set(reader.iter_package_names())
        assert reader.read_metadata("ruamel.yaml.clib") is not None

    def test_egg_info_package_discovered(self, tmp_path: Path) -> None:
        egg = tmp_path / "legacy_pkg-1.0-py3.12.egg-info"
        egg.mkdir()
        (egg / "PKG-INFO").write_text(
            "Metadata-Version: 1.0\nName: legacy-pkg\nVersion: 1.0\n"
        )
        reader = MetadataReader.from_site_packages(tmp_path)
        assert "legacy_pkg" in set(reader.iter_package_names())
        meta = reader.read_metadata("legacy-pkg")
        assert meta is not None
        assert meta.get("Version") == "1.0"

    def test_is_installed(self, tmp_path: Path) -> None:
        _make_dist_info(tmp_path, "present_pkg", "1.0.0")
        reader = MetadataReader.from_site_packages(tmp_path)
        assert reader.is_installed("present-pkg") is True
        assert reader.is_installed("absent-pkg") is False
