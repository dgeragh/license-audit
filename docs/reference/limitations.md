# Limitations

## Detection is package-level

license-audit reads what's declared in package metadata: PEP 639 fields, the legacy `License` field, trove classifiers. It does not scan `LICENSE` or `NOTICE` files inside dependencies, and it can't detect bundled or vendored code whose license differs from the package's declaration. For file-level scanning, use [ScanCode](https://github.com/nexB/scancode-toolkit).

## OSADL coverage is finite

The OSADL compatibility matrix covers about 120 well-known open-source licenses. Niche, custom, or proprietary licenses produce "Unknown" verdicts. Use `[tool.license-audit.overrides]` to assign SPDX identifiers manually when detection fails.

## OSADL is conservative

The matrix encodes a strict reading of license compatibility. For weak-copyleft licenses (LGPL, MPL) it typically excludes permissive outbound combinations even though dynamic linking or unmodified redistribution often makes those acceptable in practice. Treat the matrix as a default guardrail, not a final answer.

## License strings on PyPI are messy

PyPI packages use inconsistent license strings. license-audit normalizes 60+ common aliases to SPDX identifiers, but uncommon or malformed strings will be reported as UNKNOWN. Overrides fill the gap.

## You must provision the environment first

license-audit reads an already-installed environment; it does not resolve or install dependencies. Run `uv sync`, `poetry install`, `pip install -e .`, or equivalent before auditing. Only what's installed is audited, so a partial install yields a partial audit.

## Environment markers track the host

Dependency markers (platform, Python version, extras) are evaluated against the current runtime. Dependencies that are conditional on a different platform or Python version aren't included.

## Not legal advice

The output is informational, based on OSADL data. Real license compatibility depends on how you distribute, how you link, and what jurisdiction you're in. Treat anything this tool generates as a starting point for legal review, not the final answer.
