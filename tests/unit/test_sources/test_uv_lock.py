"""Tests for UvLockSource."""

from pathlib import Path

import pytest

from license_audit.sources.uv_lock import UvLockSource


class TestUvLockSource:
    def test_parse_real_lock(self) -> None:
        """Parse license_audit's own uv.lock."""
        lock_path = Path(__file__).parents[3] / "uv.lock"
        if not lock_path.exists():
            pytest.skip("uv.lock not found")
        source = UvLockSource(lock_path)
        specs = source.parse()
        assert len(specs) > 0
        names = {s.name for s in specs}
        assert "click" in names
        assert "pydantic" in names

    def test_pinned_versions(self) -> None:
        """Specs from uv.lock should have pinned versions."""
        lock_path = Path(__file__).parents[3] / "uv.lock"
        if not lock_path.exists():
            pytest.skip("uv.lock not found")
        source = UvLockSource(lock_path)
        specs = source.parse()
        for spec in specs:
            assert spec.version_constraint.startswith("=="), (
                f"{spec.name} has non-pinned version: {spec.version_constraint}"
            )

    def test_missing_file(self, tmp_path: Path) -> None:
        source = UvLockSource(tmp_path / "uv.lock")
        with pytest.raises(FileNotFoundError):
            source.parse()

    def test_bad_version(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text("version = 99\n")
        source = UvLockSource(lock_file)
        with pytest.raises(ValueError, match=r"Unsupported uv\.lock version"):
            source.parse()


# Minimal synthetic uv.lock with root + main dep + dev dep groups
_SYNTHETIC_LOCK = """\
version = 1

[[package]]
name = "my-project"
version = "0.1.0"
source = { virtual = "." }
dependencies = [
    { name = "click" },
]

[package.dev-dependencies]
dev = [
    { name = "ipython" },
]
test = [
    { name = "pytest" },
]

[[package]]
name = "click"
version = "8.1.7"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "ipython"
version = "8.28.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "pytest"
version = "8.3.3"
source = { registry = "https://pypi.org/simple" }
"""


class TestUvLockSourceGroupFiltering:
    def _names(self, tmp_path: Path, groups: list[str] | None) -> set[str]:
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text(_SYNTHETIC_LOCK)
        source = UvLockSource(lock_file, groups=groups)
        return {s.name for s in source.parse()}

    def test_none_includes_all(self, tmp_path: Path) -> None:
        names = self._names(tmp_path, None)
        assert names == {"click", "ipython", "pytest"}

    def test_main_only(self, tmp_path: Path) -> None:
        names = self._names(tmp_path, ["main"])
        assert names == {"click"}

    def test_dev_selector(self, tmp_path: Path) -> None:
        names = self._names(tmp_path, ["dev"])
        assert names == {"ipython"}

    def test_group_test(self, tmp_path: Path) -> None:
        names = self._names(tmp_path, ["group:test"])
        assert names == {"pytest"}

    def test_main_and_group_test(self, tmp_path: Path) -> None:
        names = self._names(tmp_path, ["main", "group:test"])
        assert names == {"click", "pytest"}

    def test_excludes_unselected_dev_group(self, tmp_path: Path) -> None:
        names = self._names(tmp_path, ["main", "group:test"])
        assert "ipython" not in names
