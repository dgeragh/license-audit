"""Tests for PixiLockSource."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_audit.sources.pixi_lock import PixiLockSource, _pixi_platform_key

# Use the host's pixi platform key so tests run consistently on any machine.
_PLATFORM = _pixi_platform_key()


def _lock(
    *,
    version: int = 6,
    default_pypi: list[str] | None = None,
    default_conda: list[str] | None = None,
    dev_pypi: list[str] | None = None,
    test_pypi: list[str] | None = None,
    noarch_pypi: list[str] | None = None,
    package_entries: list[str] | None = None,
) -> str:
    """Build synthetic pixi.lock YAML keyed to the host platform."""

    def _env_block(
        name: str,
        pypi: list[str] | None,
        conda: list[str] | None,
        noarch: list[str] | None,
    ) -> list[str]:
        lines = [
            f"  {name}:",
            "    channels:",
            "    - url: https://conda.anaconda.org/conda-forge/",
            "    packages:",
            f"      {_PLATFORM}:",
        ]
        if pypi or conda:
            for u in pypi or []:
                lines.append(f"      - pypi: {u}")
            for u in conda or []:
                lines.append(f"      - conda: {u}")
        else:
            # Empty list under platform key.
            lines[-1] = f"      {_PLATFORM}: []"
        if noarch:
            lines.append("      noarch:")
            for u in noarch:
                lines.append(f"      - pypi: {u}")
        return lines

    out: list[str] = [f"version: {version}", "environments:"]
    out.extend(_env_block("default", default_pypi, default_conda, noarch_pypi))
    if dev_pypi is not None:
        out.extend(_env_block("dev", dev_pypi, None, None))
    if test_pypi is not None:
        out.extend(_env_block("test", test_pypi, None, None))
    out.append("packages:")
    for entry in package_entries or []:
        out.append(entry)
    return "\n".join(out) + "\n"


# Reusable raw YAML package entries (each must already be indented as a top-level
# list item under ``packages:``).
_PKG_CLICK = (
    "- pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl\n"
    "  name: click\n"
    "  version: 8.1.7\n"
    "  sha256: deadbeef\n"
    "  requires_python: '>=3.7'"
)

_PKG_PYTEST = (
    "- pypi: https://files.pythonhosted.org/packages/pytest-8.0.0.whl\n"
    "  name: pytest\n"
    "  version: 8.0.0\n"
    "  sha256: deadbeef"
)

_PKG_BLACK = (
    "- pypi: https://files.pythonhosted.org/packages/black-24.0.0.whl\n"
    "  name: black\n"
    "  version: 24.0.0\n"
    "  sha256: deadbeef"
)

_PKG_TYPING = (
    "- pypi: https://files.pythonhosted.org/packages/typing_extensions-4.0.0.whl\n"
    "  name: typing-extensions\n"
    "  version: 4.0.0\n"
    "  sha256: deadbeef"
)

_PKG_NUMPY_CONDA = (
    "- conda: https://conda.anaconda.org/conda-forge/numpy-1.0.conda\n"
    "  name: numpy\n"
    "  version: 1.0.0\n"
    "  build: x"
)


class TestPixiLockSource:
    def test_parse_synthetic(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                package_entries=[_PKG_CLICK],
            )
        )
        source = PixiLockSource(lock)
        specs = source.parse()
        assert len(specs) == 1
        assert specs[0].name == "click"
        assert specs[0].version_constraint == "==8.1.7"

    def test_pinned_versions(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                package_entries=[_PKG_CLICK],
            )
        )
        for spec in PixiLockSource(lock).parse():
            assert spec.version_constraint.startswith("==")

    def test_missing_file(self, tmp_path: Path) -> None:
        source = PixiLockSource(tmp_path / "pixi.lock")
        with pytest.raises(FileNotFoundError):
            source.parse()

    def test_unsupported_lock_version(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text("version: 99\nenvironments: {}\npackages: []\n")
        with pytest.raises(ValueError, match=r"Unsupported pixi\.lock version"):
            PixiLockSource(lock).parse()

    def test_optional_selector_raises(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(_lock(default_pypi=[], package_entries=[]))
        with pytest.raises(ValueError, match=r"optional:docs"):
            PixiLockSource(lock, groups=["optional:docs"]).parse()

    def test_non_mapping_yaml_raises(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text("- 1\n- 2\n")
        with pytest.raises(ValueError, match=r"YAML mapping"):
            PixiLockSource(lock).parse()


class TestPixiLockConda:
    def test_conda_packages_skipped_with_warning(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                default_conda=[
                    "https://conda.anaconda.org/conda-forge/numpy-1.0.conda",
                    "https://conda.anaconda.org/conda-forge/scipy-1.0.conda",
                ],
                package_entries=[_PKG_CLICK, _PKG_NUMPY_CONDA],
            )
        )
        with pytest.warns(UserWarning, match=r"\d+ conda"):
            specs = PixiLockSource(lock).parse()
        assert {s.name for s in specs} == {"click"}

    def test_conda_only_lock_returns_empty_with_warning(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_conda=[
                    "https://conda.anaconda.org/conda-forge/numpy-1.0.conda"
                ],
                package_entries=[_PKG_NUMPY_CONDA],
            )
        )
        with pytest.warns(UserWarning, match=r"1 conda"):
            specs = PixiLockSource(lock).parse()
        assert specs == []

    def test_no_warning_when_no_conda(self, tmp_path: Path) -> None:
        import warnings

        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                package_entries=[_PKG_CLICK],
            )
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            PixiLockSource(lock).parse()


class TestPixiLockEnvironments:
    def test_default_maps_to_main(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                dev_pypi=["https://files.pythonhosted.org/packages/pytest-8.0.0.whl"],
                package_entries=[_PKG_CLICK, _PKG_PYTEST],
            )
        )
        names = {s.name for s in PixiLockSource(lock, groups=["main"]).parse()}
        assert names == {"click"}

    def test_named_env_via_group_selector(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                test_pypi=["https://files.pythonhosted.org/packages/pytest-8.0.0.whl"],
                package_entries=[_PKG_CLICK, _PKG_PYTEST],
            )
        )
        names = {s.name for s in PixiLockSource(lock, groups=["group:test"]).parse()}
        assert names == {"pytest"}

    def test_dev_env_via_dev_selector(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                dev_pypi=["https://files.pythonhosted.org/packages/black-24.0.0.whl"],
                package_entries=[_PKG_CLICK, _PKG_BLACK],
            )
        )
        names = {s.name for s in PixiLockSource(lock, groups=["dev"]).parse()}
        assert names == {"black"}

    def test_package_only_in_unselected_env_excluded(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                dev_pypi=["https://files.pythonhosted.org/packages/black-24.0.0.whl"],
                package_entries=[_PKG_CLICK, _PKG_BLACK],
            )
        )
        names = {s.name for s in PixiLockSource(lock, groups=["main"]).parse()}
        assert "black" not in names

    def test_no_groups_includes_all_environments(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                dev_pypi=["https://files.pythonhosted.org/packages/black-24.0.0.whl"],
                test_pypi=["https://files.pythonhosted.org/packages/pytest-8.0.0.whl"],
                package_entries=[_PKG_CLICK, _PKG_BLACK, _PKG_PYTEST],
            )
        )
        names = {s.name for s in PixiLockSource(lock).parse()}
        assert names == {"click", "black", "pytest"}


class TestPixiLockPlatform:
    def test_noarch_always_included(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[],
                noarch_pypi=[
                    "https://files.pythonhosted.org/packages/typing_extensions-4.0.0.whl"
                ],
                package_entries=[_PKG_TYPING],
            )
        )
        names = {s.name for s in PixiLockSource(lock).parse()}
        assert names == {"typing_extensions"}

    def test_other_platform_packages_excluded(self, tmp_path: Path) -> None:
        # Build YAML manually that puts a package only on a non-host platform.
        other = "linux-64" if _PLATFORM != "linux-64" else "osx-arm64"
        yaml_text = (
            "version: 6\n"
            "environments:\n"
            "  default:\n"
            "    channels:\n"
            "    - url: https://conda.anaconda.org/conda-forge/\n"
            "    packages:\n"
            f"      {other}:\n"
            "      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl\n"
            "packages:\n"
            f"{_PKG_CLICK}\n"
        )
        lock = tmp_path / "pixi.lock"
        lock.write_text(yaml_text)
        specs = PixiLockSource(lock).parse()
        assert specs == []

    def test_unknown_platform_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from license_audit.sources import pixi_lock as pl

        monkeypatch.setattr(pl.sys, "platform", "haiku")
        monkeypatch.setattr(pl.platform, "machine", lambda: "exotic")
        lock = tmp_path / "pixi.lock"
        lock.write_text("version: 6\nenvironments: {}\npackages: []\n")
        with pytest.raises(ValueError, match=r"Unsupported host platform"):
            PixiLockSource(lock).parse()


class TestPixiLockFormatV5:
    """v5 lock files use ``kind: pypi|conda`` with a separate ``url`` field."""

    def test_v5_pypi_kind_entries(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(f"""\
version: 5
environments:
  default:
    channels:
    - url: https://conda.anaconda.org/conda-forge/
    packages:
      {_PLATFORM}:
      - pypi: https://files.pythonhosted.org/packages/click-8.1.7.whl
packages:
- kind: pypi
  name: click
  version: 8.1.7
  url: https://files.pythonhosted.org/packages/click-8.1.7.whl
  sha256: deadbeef
""")
        specs = PixiLockSource(lock).parse()
        assert len(specs) == 1
        assert specs[0].name == "click"
        assert specs[0].version_constraint == "==8.1.7"


class TestPixiLockDedup:
    def test_package_in_multiple_envs_not_duplicated(self, tmp_path: Path) -> None:
        lock = tmp_path / "pixi.lock"
        lock.write_text(
            _lock(
                default_pypi=[
                    "https://files.pythonhosted.org/packages/click-8.1.7.whl"
                ],
                dev_pypi=["https://files.pythonhosted.org/packages/click-8.1.7.whl"],
                package_entries=[_PKG_CLICK],
            )
        )
        specs = PixiLockSource(lock).parse()
        assert len(specs) == 1
        assert specs[0].name == "click"


_FIXTURE = Path(__file__).parents[2] / "fixtures" / "pixi.lock"


class TestPixiLockFixture:
    """Regression tests against a committed real-world pixi.lock fixture.

    The fixture references the same set of pypi URLs from every supported
    platform key, so these assertions are stable regardless of the host.
    """

    def test_parses_with_conda_warning(self) -> None:
        with pytest.warns(UserWarning, match=r"\d+ conda"):
            specs = PixiLockSource(_FIXTURE).parse()
        assert len(specs) > 0

    def test_default_env_pypi_packages(self) -> None:
        with pytest.warns(UserWarning):
            specs = PixiLockSource(_FIXTURE, groups=["main"]).parse()
        names = {s.name for s in specs}
        assert {"click", "typing_extensions"}.issubset(names)
        assert "pytest" not in names

    def test_group_test_isolates_test_env(self) -> None:
        # No conda entries are referenced from the test env, so no warning.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            specs = PixiLockSource(_FIXTURE, groups=["group:test"]).parse()
        assert {s.name for s in specs} == {"pytest"}

    def test_all_versions_pinned(self) -> None:
        with pytest.warns(UserWarning):
            specs = PixiLockSource(_FIXTURE).parse()
        for spec in specs:
            assert spec.name
            assert spec.version_constraint.startswith("==")
