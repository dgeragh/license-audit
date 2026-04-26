# How it works

1. **Parse** - Reads your dependency specifier (`uv.lock`, `poetry.lock`, `pixi.lock`, `requirements.txt`, `pyproject.toml`, or an existing environment).
2. **Provision** - Creates a temporary environment with uv and installs the dependencies. Skipped when analyzing a venv or the current environment directly.
3. **Detect** - Walks `site-packages`, reading each package's METADATA to identify licenses via PEP 639 `License-Expression`, the `License` field, trove classifiers, or user overrides.
4. **Classify** - Categorizes licenses as permissive, weak-copyleft, strong-copyleft, or network-copyleft using OSADL copyleft data.
5. **Analyze** - Checks pairwise compatibility using the OSADL matrix and flags conflicts. For OR expressions (for example `MIT OR GPL-2.0`), picks the most permissive alternative.
6. **Recommend** - Determines the most permissive outbound license that satisfies every dependency constraint.
7. **Report** - Presents findings as terminal output, Markdown, JSON, or third-party notices.
