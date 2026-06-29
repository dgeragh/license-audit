# Commands

license-audit provides the five commands detailed below. All accept the global flags `--target`, `--policy`, and `--config`.

## `analyze`

Default analysis output: a per-package table with version, license expression, category, source, and parent, plus recommended outbound licenses, action items, and a summary. Pass `--format json` for the same analysis as machine-readable JSON.

```bash
license-audit analyze
license-audit analyze --format json
license-audit --target /path/to/project analyze
license-audit --target /path/to/.venv analyze
```

## `check`

License policy gate for CI. See [CI integration](ci-integration.md) for the full guide.

```bash
license-audit check
license-audit check --fail-on-unknown      # explicit (default)
license-audit check --no-fail-on-unknown   # tolerate unknown licenses
```

Exit codes: `0` = pass, `1` = policy violation (incompatible pairs, denied licenses, or category exceeded), `2` = unknown licenses (when `--fail-on-unknown`).

## `recommend`

Outbound license recommendation based on the most restrictive dependency.

```bash
license-audit recommend
```

The output names the single most restrictive dependency, lists compatible outbound licenses ranked by permissiveness, and prints guidance specific to the strongest copyleft level present (e.g. weak-copyleft caveats for LGPL/MPL trees, attribution suggestions for fully permissive trees).

## `report`

Compliance document for distribution or review.

```bash
license-audit report                                       # markdown to stdout
license-audit report --format json                         # JSON to stdout
license-audit report --format notices                      # notices to stdout
license-audit report --output COMPLIANCE.md                # write to file
license-audit report --format notices --output NOTICES.md
```

| Format | Use case |
|---|---|
| `markdown` (default) | Human-readable compliance summary. Includes a **Licenses Requiring Review** section with the full license text of any dependency whose license could not be mapped to SPDX. |
| `json` | Machine-readable, suitable for downstream tooling |
| `notices` | `THIRD_PARTY_NOTICES.md` with full license texts |

## `refresh`

Re-downloads the OSADL compatibility matrix and copyleft data into the user cache. Run after upgrading license-audit, or whenever you suspect the bundled data is stale.

```bash
license-audit refresh
```

The command writes to a platform-appropriate cache directory (resolved via `platformdirs`).

## Global flags

These apply to every command:

| Flag | Purpose |
|---|---|
| `--target PATH` | Project directory or virtualenv to analyze. See [target resolution](configuration.md#target-resolution). |
| `--policy LEVEL` | Override the configured policy level (`permissive`, `weak-copyleft`, `strong-copyleft`, `network-copyleft`). |
| `--config PATH` | `pyproject.toml` (or its directory) to read config and the project name from. See [target resolution](configuration.md#target-resolution). |
| `--version` | Print version and exit. |
