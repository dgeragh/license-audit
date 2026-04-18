# CI integration

`license-audit check` is designed for CI pipelines. It returns distinct exit codes so a pipeline can differentiate real violations from packages whose license couldn't be detected.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | All dependencies pass the policy |
| `1` | Policy violation (incompatible pairs, denied licenses, or category exceeded) |
| `2` | Unknown licenses detected (when `fail-on-unknown = true`) |

## GitHub Actions

Minimal setup:

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

Surface the compliance report as a PR job summary (runs even when `check` fails):

```yaml
      - name: Compliance summary
        if: always()
        run: uv run license-audit report --format markdown >> $GITHUB_STEP_SUMMARY
```

Upload the compliance report and notices file as build artifacts:

```yaml
      - name: Generate reports
        if: always()
        run: |
          uv run license-audit report --output COMPLIANCE.md
          uv run license-audit report --format notices --output THIRD_PARTY_NOTICES.md
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: license-report
          path: |
            COMPLIANCE.md
            THIRD_PARTY_NOTICES.md
```

## GitLab CI

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

## pre-commit hook

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

Running on `pre-push` (not `pre-commit`) keeps commits fast and only checks once before pushing.

## Branching on exit codes

Exit `2` is distinct from `1` so CI can treat undetected licenses differently from policy violations:

```bash
uv run license-audit check
ec=$?
case $ec in
  0) ;;
  1) echo "::error::License policy violation"; exit 1 ;;
  2) echo "::warning::Unknown licenses - add overrides in pyproject.toml"; exit 0 ;;
esac
```

## Running different policies in separate jobs

Use the `--policy` flag to set the level without touching `pyproject.toml`:

```yaml
- name: Strict permissive check
  run: uv run license-audit --policy permissive check

- name: Allow weak copyleft
  run: uv run license-audit --policy weak-copyleft check
```

Available levels: `permissive`, `weak-copyleft`, `strong-copyleft`, `network-copyleft`.

## Adding a new dependency: workflow

The typical flow when introducing a new package:

1. `uv add <package>` (or edit `pyproject.toml` and `uv sync`).
2. Run `uv run license-audit check` locally.
3. Handle the outcome:
   - **Exit 0:** commit and push.
   - **Exit 2 (unknown):** the tool couldn't detect an SPDX identifier. Add an override in `pyproject.toml` once you've confirmed the license:
     ```toml
     [tool.license-audit.overrides]
     new-package = "MIT"
     ```
   - **Exit 1 (policy violation):** either swap the dependency for a differently-licensed alternative, add the license to `allowed-licenses`, or relax `policy` (for example `permissive` to `weak-copyleft`) if that fits your project.

## Check flags

```bash
uv run license-audit check                        # default: fail on unknowns
uv run license-audit check --no-fail-on-unknown   # tolerate unknowns (exit 0 if only unknowns, exit 1 if policy violations)
uv run license-audit check --fail-on-unknown      # explicit opt-in
```

The flag takes precedence over `fail-on-unknown` in `pyproject.toml`.
