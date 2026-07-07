# Contributing to license-audit

Thanks for your interest in contributing! This document covers the basics to get you started.

## Development Setup

Clone the repo and install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/dgeragh/license-audit.git
cd license-audit
uv sync --all-groups
```

## Running Tests and Linting

```bash
# Run tests with coverage
uv run pytest tests/ --cov

# Lint and format
uv run ruff check
uv run ruff format

# Type check
uv run mypy
```

All of these must pass before a PR will be merged.

## Making Changes

1. Fork the repo and create a branch from `main`.
2. Make your changes. Add or update tests as appropriate.
3. If you change the report models, regenerate `docs/reference/report-schema.json` with `UPDATE_SCHEMA=1 uv run pytest tests/unit/test_reports/test_schema_contract.py` and update `docs/reference/report-schema.md`.
4. Run the full check suite (tests, ruff, mypy) locally.
5. Open a pull request with a clear description of what you changed and why.

## Reporting Bugs

Open an issue with:

- What you ran (command, Python version, OS)
- What you expected
- What happened instead
- The output of `license-audit --version`

## Requesting Features

Open an issue describing the use case. Explain what problem it solves rather than jumping straight to a proposed solution.

## Code Style

- Ruff handles formatting and linting.
- Type annotations on all public functions.
- Keep dependencies minimal.
