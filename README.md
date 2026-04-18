# license-audit

**Analyze dependency licenses and get actionable licensing guidance for Python projects.**

license-audit goes beyond simply listing dependency licenses. It tells you what license your project needs, flags incompatible combinations, and generates compliance documents.

## Features

- **License Detection** - Automatically detects licenses for all transitive dependencies using PEP 639 metadata, trove classifiers, and configurable overrides
- **Compatibility Analysis** - Uses the [OSADL compatibility matrix](https://www.osadl.org/Access-to-raw-data.oss-compliance-raw-data-access.0.html) (covers ~120 well-known licenses) to check whether your dependency licenses are compatible with each other
- **License Recommendations** - Tells you the most permissive license your project can use given its dependencies
- **Compliance Reports** - Generate Markdown, JSON, or third-party notices reports documenting your project's license posture
- **CI Integration** - `license-audit check` provides exit codes suitable for CI/CD pipelines
- **Modern Tooling** - First-class support for uv, pyproject.toml, and PEP 639

## Installation

```bash
pip install license-audit
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add license-audit --dev
```

## Usage

### Analyze dependencies

By default, license-audit analyzes the current Python environment:

```bash
license-audit analyze
license-audit analyze --format json    # JSON output
```

Use `--target` to point at a specific project directory, dependency file, or virtual environment:

```bash
license-audit --target .                        # auto-detect from current dir
license-audit --target /path/to/project         # auto-detect from project dir
license-audit --target /path/to/uv.lock         # parse a specific lockfile
license-audit --target /path/to/requirements.txt  # parse a requirements file
license-audit --target /path/to/.venv           # analyze an existing venv directly
```

When given a dependency file or project directory, license-audit creates a temporary environment with uv, installs the dependencies, and analyzes that environment. When given a venv, it analyzes directly without creating anything.

Example output:

```bash
license-audit analyze
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
│ requests │ 2.32.3  │ Apache-2.0   │ permissive │ pep639 │ (direct) │
│ numpy    │ 1.26.4  │ BSD-3-Clause │ permissive │ pep639 │ (direct) │
│ celery   │ 5.4.0   │ BSD-3-Clause │ permissive │ pep639 │ (direct) │
└──────────┴─────────┴──────────────┴────────────┴────────┴──────────┘

Recommended Outbound Licenses (most -> least permissive):
  -> MIT
     BSD-3-Clause
     Apache-2.0
     ISC
     0BSD
  ... and 84 more

──────────────────────────── Summary ────────────────────────────
  Total dependencies: 6
  Unknown licenses:   0
  Copyleft licenses:  0
  Policy check:       PASSED
```

### Get a license recommendation

Find out the most permissive license your project can use:

```bash
license-audit recommend
```

```
──────────────────── License Recommendation: my-project ────────────────────

Compatible licenses for your project:
  -> MIT (permissive) <- recommended
    BSD-3-Clause (permissive)
    Apache-2.0 (permissive)
    ISC (permissive)
    0BSD (permissive)

+------------------------------------------------------------------------+
|                              Guidance                                  |
| All your dependencies use permissive licenses. You are free to choose  |
| any license, including proprietary.                                    |
|                                                                        |
| Common choices: MIT (simplest), Apache-2.0 (patent grant),             |
| BSD-3-Clause (attribution).                                            |
+------------------------------------------------------------------------+
```

When your dependencies include copyleft licenses, the recommendation adapts:

```
──────────────────── License Recommendation: my-project ────────────────────

Most restrictive dependency: pandas-stubs (GPL-3.0-or-later)
  Your entire project must use a compatible copyleft license.

Compatible licenses for your project:
  -> GPL-3.0-or-later (strong-copyleft) <- recommended
    GPL-3.0-only (strong-copyleft)
    AGPL-3.0-only (network-copyleft)
    AGPL-3.0-or-later (network-copyleft)

+------------------------------------------------------------------------+
|                              Guidance                                  |
| You have strong-copyleft dependencies (e.g., GPL). Your entire project |
| must be licensed under a GPL-compatible license.                       |
|                                                                        |
| If this is not acceptable, you must find alternative dependencies with |
| permissive licenses.                                                   |
+------------------------------------------------------------------------+
```

### CI policy check

Use `license-audit check` in CI pipelines for automated compliance gating:

```bash
license-audit check
license-audit check --no-fail-on-unknown     # allow unknown licenses
```

Override the policy level from the command line (takes precedence over `pyproject.toml`):

```bash
license-audit --policy permissive check          # only permissive licenses allowed
license-audit --policy weak-copyleft check       # allow LGPL, MPL, etc.
license-audit --policy strong-copyleft check     # allow GPL, etc.
license-audit --policy network-copyleft check    # allow AGPL, etc.
```

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | All dependencies pass the license policy |
| `1` | Policy violation (incompatible or denied licenses) |
| `2` | Unknown licenses detected (when `fail-on-unknown = true`) |

#### GitHub Actions example

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

To surface the compliance report as a PR job summary (runs even when `check` fails):

```yaml
      - name: Compliance summary
        if: always()
        run: uv run license-audit report --format markdown >> $GITHUB_STEP_SUMMARY
```

#### GitLab CI example

```yaml
license-check:
  image: python:3.12
  before_script:
    - pip install uv
    - uv sync --locked
  script:
    - uv run license-audit check
    - uv run license-audit report --format markdown --output compliance.md
  artifacts:
    when: always
    paths:
      - compliance.md
```

#### pre-commit hook

Catch violations locally before they reach CI. Add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: license-audit
      name: license-audit
      entry: uv run license-audit check
      language: system
      pass_filenames: false
      stages: [pre-push]
```

`pre-push` keeps commits fast and only runs `check` once before pushing.

#### Branching on exit codes

Exit `2` lets CI distinguish undetected licenses from outright policy violations. For example, to fail the build on real violations but only warn on unknowns:

```bash
uv run license-audit check
ec=$?
case $ec in
  0) ;;
  1) echo "::error::License policy violation"; exit 1 ;;
  2) echo "::warning::Unknown licenses - add overrides in pyproject.toml"; exit 0 ;;
esac
```

#### Adding a new dependency

Typical workflow when introducing a new package:

1. `uv add <package>` (or edit `pyproject.toml` and `uv sync`).
2. Run `uv run license-audit check` locally.
3. Handle the outcome:
   - **Exit 0:** commit and push.
   - **Exit 2 (unknown):** the tool couldn't detect an SPDX identifier. Add an override in `pyproject.toml` once you've confirmed the license:
     ```toml
     [tool.license-audit.overrides]
     new-package = "MIT"
     ```
   - **Exit 1 (policy violation):** either swap the dependency for a differently-licensed alternative, add the license to `allowed-licenses`, or relax `policy` (e.g. `permissive` → `weak-copyleft`) if that suits your project.

### Generate a compliance report

Produce a Markdown or JSON compliance document:

```bash
license-audit report --output COMPLIANCE.md
license-audit report --format json --output compliance.json
```

The Markdown report includes a dependency table, classification breakdown, compatibility analysis, recommended licenses, and action items.

### Generate a third-party notices file

Bundle all dependency license texts into a single attribution file for distribution with your software:

```bash
license-audit report --format notices --output THIRD_PARTY_NOTICES.md
```

The notices file includes the full license text for each dependency, pulled from PEP 639 `License-File` metadata or common license file names (LICENSE, COPYING, NOTICE) in each package's dist-info directory.

### Update OSADL data

Download the latest OSADL data into the user cache (used in preference to the bundled copy):

```bash
license-audit refresh
```

## Configuration

Add to your `pyproject.toml`:

```toml
[tool.license-audit]
fail-on-unknown = true                  # fail check when licenses can't be detected
policy = "permissive"                   # "permissive" | "weak-copyleft" | "strong-copyleft" | "network-copyleft"
allowed-licenses = ["MIT", "Apache-2.0", "BSD-3-Clause"]
denied-licenses = ["GPL-3.0-only"]
dependency-groups = ["main", "optional:api"]  # only check specific groups (default: all)

[tool.license-audit.overrides]
some-internal-package = "MIT"           # manual override for undetectable licenses
dual-licensed-pkg = "Apache-2.0 OR MIT" # SPDX expressions supported
```

#### Dependency group selectors

| Selector | Maps to |
|---|---|
| `main` | `[project.dependencies]` |
| `optional:<name>` | `[project.optional-dependencies.<name>]` |
| `group:<name>` | `[dependency-groups.<name>]` (PEP 735) |
| `dev` | `[tool.uv.dev-dependencies]` |

CLI override (repeatable):

```bash
license-audit --dependency-groups main --dependency-groups group:test check
```

### Target resolution

The `--target` flag determines what to analyze. The source type is inferred automatically:

| Target | Behavior |
|--------|----------|
| *(none)* | Analyze the current Python environment directly |
| Project directory | Auto-detect: tries `uv.lock` -> `requirements.txt` -> `pyproject.toml` -> `.venv` |
| `uv.lock` | Parse lockfile, create temp environment, analyze |
| `requirements.txt` | Parse requirements, create temp environment, analyze |
| `pyproject.toml` | Parse `[project.dependencies]`, optional-dependencies, dependency-groups, and `[tool.uv.dev-dependencies]`, create temp environment, analyze |
| `.venv` directory | Analyze the venv directly (no temp environment) |

In all cases, `[tool.license-audit]` configuration is loaded from the target project's `pyproject.toml`.

## How it works

1. **Parse** - Reads your dependency specifier (`uv.lock`, `requirements.txt`, `pyproject.toml`, or an existing environment)
2. **Provision** - Creates a temporary environment with uv and installs the dependencies (skipped when analyzing a venv or the current environment directly)
3. **Detect** - Walks `site-packages`, reading each package's METADATA to identify licenses (PEP 639 `License-Expression`, `License` field, trove classifiers, or user overrides)
4. **Classify** - Categorizes licenses as permissive, weak-copyleft, strong-copyleft, or network-copyleft using OSADL copyleft data
5. **Analyze** - Checks pairwise compatibility using the OSADL matrix and identifies conflicts. For OR expressions (e.g., `MIT OR GPL-2.0`), picks the most permissive alternative
6. **Recommend** - Determines the most permissive outbound license that satisfies all dependency constraints
7. **Report** - Presents findings as terminal output, Markdown, or JSON with actionable guidance

## Comparison with other tools

| Capability | license-audit | [ScanCode](https://github.com/nexB/scancode-toolkit) | [pip-licenses](https://github.com/raimon49/pip-licenses) | [liccheck](https://github.com/dhatim/python-liccheck) |
|---|---|---|---|---|
| License detection from package metadata | Yes | No (file-level) | Yes | Yes |
| File-level license scanning | No | Yes | No | No |
| Pairwise compatibility analysis (OSADL) | Yes | No | No | No |
| Outbound license recommendation | Yes | No | No | No |
| Transitive dependency tree with parents | Yes | N/A | No | No |
| Dual-license resolution (OR expressions) | Yes (picks most permissive) | N/A | No | No |
| CI policy gating with exit codes | Yes | Via scripting | Via flags | Yes |
| Compliance report generation | Markdown, JSON, notices | JSON, HTML, CSV, SPDX | CSV, JSON, Markdown | No |
| Allow/deny lists | Yes | Via scripting | No | Yes |
| Dependency group filtering | Yes (main, dev, optional, PEP 735) | N/A | No | No |
| Language support | Python | Any | Python | Python |
| `pyproject.toml` configuration | Yes | No | No | Yes |
| uv / PEP 639 support | Yes | No | No | No |

**In short:** license-audit is designed for Python teams that want actionable compliance guidance, not just "what licenses do I have?" but "what can I ship, and do my dependencies conflict?" If you need file-level scanning across a polyglot codebase, ScanCode is the right tool for that job and complements license-audit well.

## Limitations

- **Package-level detection only** - license-audit reads the license declared in package metadata (PEP 639, `License` field, trove classifiers). It does not scan `THIRD_PARTY_NOTICES`, `NOTICE`, or `LICENSE` files inside dependencies, and cannot detect bundled/vendored code with a different license than the package declares. For file-level license scanning, see [ScanCode](https://github.com/nexB/scancode-toolkit).

- **OSADL matrix coverage** - The OSADL compatibility matrix covers roughly 120 well-known open-source licenses. Niche, custom, or proprietary licenses will produce "Unknown" compatibility verdicts. Use `[tool.license-audit.overrides]` to manually assign SPDX identifiers when detection fails.

- **License string normalization** - PyPI packages use wildly inconsistent license strings. license-audit maps 50+ common aliases to SPDX identifiers, but uncommon or malformed strings may not be recognized and will be reported as UNKNOWN. Overrides can fill these gaps.

- **requirements.txt is flat** - When analyzing a `requirements.txt`, only direct dependencies listed in the file are parsed. Transitive dependencies are resolved by installing into a temporary environment, but the initial spec list comes from the file as written.

- **uv.lock format stability** - `uv.lock` does not have a formal specification. The parser supports version 1 of the lock format and will fail explicitly on unrecognized versions.

- **Environment markers** - Dependency markers (platform, Python version, extras) are evaluated against the current runtime environment. Dependencies that are conditional on a different platform or Python version will not be included.

- **uv required for temp environments** - When analyzing a dependency file or project directory (rather than a venv or the current environment), license-audit creates a temporary environment using uv. If uv is not installed, these targets will fail. Direct venv and current-environment analysis do not require uv.

- **No legal advice** - license-audit provides informational analysis based on OSADL compatibility data. It is not a substitute for legal review. License compatibility can depend on distribution method, linking type, and jurisdiction - factors this tool does not evaluate.

## License

MIT - see [LICENSE](LICENSE) for details.

This project bundles data from the [OSADL Open Source License Obligations Checklists](https://www.osadl.org/Checklists) project, licensed under CC-BY-4.0. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full attribution.
