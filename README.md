# license-audit

**Analyze dependency licenses for Python projects.**

license-audit tells you what license your project can use, flags incompatible combinations, and generates compliance documents suitable for CI gating.

## Features

- License detection across the full transitive tree, from PEP 639 metadata, the legacy `License` field, trove classifiers, and user overrides.
- Pairwise compatibility checking against the [OSADL compatibility matrix](https://www.osadl.org/Access-to-raw-data.oss-compliance-raw-data-access.0.html) (~120 licenses).
- Outbound license recommendations ranked by permissiveness.
- Compliance reports as Markdown, JSON, or third-party-notices.
- CI exit codes that distinguish policy violations from undetected licenses.
- Reads the licenses straight from your installed environment: provision it however you like (`uv`, Poetry, pip), then point license-audit at it.

## Installation

```bash
pip install license-audit
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add license-audit --dev
```

## Quickstart

Provision your dependencies first, then run license-audit inside that environment:

```bash
uv sync
uv run license-audit analyze
```

Or point it at an existing virtualenv:

```bash
license-audit --target .venv analyze
```

```
License Analysis: my-project

Dependency Licenses
  Package   Version  License        Category    Source  Parent
  click     8.1.7    BSD-3-Clause   permissive  pep639  (direct)
  pydantic  2.9.2    MIT            permissive  pep639  (direct)
  rich      13.9.4   MIT            permissive  pep639  (direct)

Recommended Outbound Licenses (most -> least permissive):
  -> MIT
     Apache-2.0
     BSD-2-Clause
     ...

Summary
  Total dependencies: 3
  Unknown licenses:   0
  Copyleft licenses:  0
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
| `1` | Policy violation (incompatible pairs, denied licenses, or category exceeded) |
| `2` | Unknown licenses detected (when `fail-on-unknown = true`) |

For GitLab, pre-commit, handling unknowns, and the new-dependency workflow, see the [CI integration guide](https://dgeragh.github.io/license-audit/latest/user-guide/ci-integration/).

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

Full reference: [user guide -> configuration](https://dgeragh.github.io/license-audit/latest/user-guide/configuration/).

## Documentation

Full documentation lives at **https://dgeragh.github.io/license-audit**:

- [Configuration reference](https://dgeragh.github.io/license-audit/latest/user-guide/configuration/)
- [CI integration guide](https://dgeragh.github.io/license-audit/latest/user-guide/ci-integration/)
- [How it works](https://dgeragh.github.io/license-audit/latest/reference/how-it-works/)
- [Comparison with other tools](https://dgeragh.github.io/license-audit/latest/reference/comparison/)
- [Limitations](https://dgeragh.github.io/license-audit/latest/reference/limitations/)

## License

MIT. See [LICENSE](https://github.com/dgeragh/license-audit/blob/main/LICENSE).

This project bundles data from the [OSADL Open Source License Obligations Checklists](https://www.osadl.org/Checklists) project, licensed under CC-BY-4.0. See [THIRD_PARTY_NOTICES.md](https://github.com/dgeragh/license-audit/blob/main/THIRD_PARTY_NOTICES.md) for full attribution.
