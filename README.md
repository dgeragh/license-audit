# license-audit

**Analyze dependency licenses and get actionable licensing guidance for Python projects.**

license-audit tells you what license your project can use, flags incompatible combinations, and generates compliance documents suitable for CI gating.

## Features

- **License detection** from PEP 639 metadata, trove classifiers, and user overrides across the full transitive dependency tree.
- **Compatibility analysis** using the [OSADL compatibility matrix](https://www.osadl.org/Access-to-raw-data.oss-compliance-raw-data-access.0.html) (covers ~120 well-known licenses).
- **Outbound license recommendations** ranked by permissiveness.
- **Compliance reports** in Markdown, JSON, or third-party-notices form.
- **CI-ready** with distinct exit codes for policy violations and undetected licenses.
- **Support** for `uv.lock`, `poetry.lock`, `pixi.lock`, `pyproject.toml`, `requirements.txt`, and PEP 639.

## Installation

```bash
pip install license-audit
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add license-audit --dev
```

## Quickstart

Run against the current project directory:

```bash
license-audit --target . analyze
```

```
──────────────────── License Analysis: my-project ────────────────────

                        Dependency Licenses
┏━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Package  ┃ Version ┃ License      ┃ Category   ┃ Source ┃ Parent   ┃
┡━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ click    │ 8.1.7   │ BSD-3-Clause │ permissive │ pep639 │ (direct) │
│ pydantic │ 2.9.2   │ MIT          │ permissive │ pep639 │ (direct) │
│ rich     │ 13.9.4  │ MIT          │ permissive │ pep639 │ (direct) │
└──────────┴─────────┴──────────────┴────────────┴────────┴──────────┘

Recommended Outbound Licenses (most -> least permissive):
  -> MIT
     BSD-3-Clause
     Apache-2.0
     ...

──────────────────────────── Summary ────────────────────────────
  Total dependencies: 3
  Policy check:       PASSED
```

## CI quickstart

Add to your pipeline to gate on license policy:

```yaml
jobs:
  license-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --locked
      - run: uv run license-audit check
```

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | All dependencies pass the policy |
| `1` | Policy violation (incompatible pairs or denied licenses) |
| `2` | Unknown licenses detected (when `fail-on-unknown = true`) |

For GitLab CI, pre-commit hooks, handling unknowns, and the "adding a new dependency" workflow, see the [CI integration guide](https://dgeragh.github.io/license-audit/user-guide/ci-integration/).

## Configuration

```toml
[tool.license-audit]
fail-on-unknown = true
policy = "permissive"  # permissive | weak-copyleft | strong-copyleft | network-copyleft
allowed-licenses = ["MIT", "Apache-2.0", "BSD-3-Clause"]
denied-licenses = ["GPL-3.0-only"]

[tool.license-audit.overrides]
some-internal-package = "MIT"
dual-licensed-pkg = "Apache-2.0 OR MIT"

[tool.license-audit.ignored-packages]
pandas-stubs = "Stubs only, not redistributed"
```

Full configuration reference: [user guide -> configuration](https://dgeragh.github.io/license-audit/user-guide/configuration/).

## Documentation

Full documentation lives at **https://dgeragh.github.io/license-audit**:

- [Configuration reference](https://dgeragh.github.io/license-audit/user-guide/configuration/) - all options, target resolution, dependency group selectors.
- [CI integration guide](https://dgeragh.github.io/license-audit/user-guide/ci-integration/) - GitHub Actions, GitLab, pre-commit, new-dependency workflow.
- [How it works](https://dgeragh.github.io/license-audit/reference/how-it-works/) - the detection and analysis pipeline.
- [Comparison with other tools](https://dgeragh.github.io/license-audit/reference/comparison/) - ScanCode, pip-licenses, liccheck.
- [Limitations](https://dgeragh.github.io/license-audit/reference/limitations/) - what the tool does and doesn't cover.

## License

MIT - see [LICENSE](https://github.com/dgeragh/license-audit/blob/main/LICENSE).

This project bundles data from the [OSADL Open Source License Obligations Checklists](https://www.osadl.org/Checklists) project, licensed under CC-BY-4.0. See [THIRD_PARTY_NOTICES.md](https://github.com/dgeragh/license-audit/blob/main/THIRD_PARTY_NOTICES.md) for full attribution.
