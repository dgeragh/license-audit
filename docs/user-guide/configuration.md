# Configuration

license-audit is configured via `[tool.license-audit]` in your `pyproject.toml`.

Configuration is loaded from the target's location: a project directory uses its own `pyproject.toml`, and a virtualenv uses the `pyproject.toml` beside it. Use `--config` to read config from elsewhere — handy when the virtualenv lives outside your project. If no config is found, defaults apply.

## Options

### `fail-on-unknown`

Whether the `check` command fails when a dependency has an undetectable license. Default: `true`.

### `policy`

License policy preset. Default: `"permissive"`.

| Value | Description |
|-------|-------------|
| `"permissive"` | Only allow permissive licenses (MIT, BSD, Apache, etc.) |
| `"weak-copyleft"` | Allow permissive + weak copyleft (LGPL, MPL, etc.) |
| `"strong-copyleft"` | Allow permissive + weak + strong copyleft (GPL, etc.) |
| `"network-copyleft"` | Allow all open-source licenses including AGPL |

Each preset sets the maximum copyleft level allowed; anything above the threshold fails the check.

The `--policy` CLI flag overrides this setting:

```bash
license-audit --policy weak-copyleft check
```

### `allowed-licenses`

Explicit list of allowed SPDX identifiers. When set, only these licenses pass the policy check, narrowing whatever `policy` would otherwise allow.

### `denied-licenses`

SPDX identifiers that always fail the policy check, regardless of `policy` or `allowed-licenses`.

### Choosing dependency groups

Selecting which dependency groups to audit happens when you provision: install only the groups you care about, then audit that environment. For example, `uv sync --no-dev` for a production-only audit, or `uv sync --all-groups` to include everything.

### `target`

Default `--target` to use when none is supplied on the CLI. Relative paths resolve against the directory containing `pyproject.toml`.

```toml
[tool.license-audit]
target = "."
```

The CLI `--target` flag overrides this setting:

```bash
license-audit --target /path/to/other check
```

When `target` is unset and `--target` is omitted, license-audit falls back to analyzing the active Python environment (see "Target resolution" below).

### `overrides`

Manual license assignments for packages where auto-detection fails.

```toml
[tool.license-audit.overrides]
my-internal-package = "MIT"
dual-licensed-pkg = "Apache-2.0 OR MIT"
```

### `ignored-packages`

Exempt specific packages from policy evaluation. Each entry is a reason string that ends up in the audit trail.

```toml
[tool.license-audit.ignored-packages]
pandas-stubs = "Stubs only, not redistributed"
internal-tool = "Vendored, excluded from dist"
```

Ignored packages are skipped by `check`'s policy evaluation (no exit 1 or 2), excluded from incompatible-pair analysis (so they don't constrain recommendations), and still listed in every report (terminal, markdown, JSON, notices) with an `ignored` marker plus the reason.

The reason is required and must be non-empty; empty reasons are rejected at config load. Package names are canonicalized per PEP 503, so `pandas-stubs`, `pandas_stubs`, and `Pandas.Stubs` all match.

Use `overrides` when you want to re-assert what the license is. Use `ignored-packages` when the license is correct but doesn't apply to your situation (e.g. the package isn't shipped, or you've reviewed it manually and accepted the risk).

## Target resolution

license-audit always reads an **installed environment**. Provision your dependencies first (`uv sync`, `poetry install`, `pip install -e .`, ...), then point license-audit at the result. `--target` selects the environment:

| Target | Behavior |
|--------|----------|
| *(none)* | Audit `./.venv` if present, otherwise the Python environment running license-audit |
| Project directory | Audit `<dir>/.venv` (errors if there is no virtualenv to read) |
| Virtualenv directory | Audit that virtualenv directly |
| A file | Rejected — point at a project directory or virtualenv instead |

`--config` decouples where config and the project name come from. By default they follow the target (a project directory, or a virtualenv's parent); pass `--config path/to/pyproject.toml` to override, which is useful when the virtualenv lives outside your project.

Examples:

```bash
license-audit analyze                                   # ./.venv, else the active environment
uv run license-audit analyze                            # the project's own environment
license-audit --target /path/to/project analyze         # that project's .venv
license-audit --target /path/to/.venv analyze           # an existing virtualenv
license-audit --target /ext/.venv --config . analyze    # external venv, this project's policy
```
