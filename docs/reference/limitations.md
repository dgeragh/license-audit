# Limitations

- **Package-level detection only.** license-audit reads the license declared in package metadata (PEP 639, `License` field, trove classifiers). It does not scan `THIRD_PARTY_NOTICES`, `NOTICE`, or `LICENSE` files inside dependencies and cannot detect bundled or vendored code whose license differs from the package's declared one. For file-level scanning, see [ScanCode](https://github.com/nexB/scancode-toolkit).

- **OSADL matrix coverage.** The OSADL compatibility matrix covers roughly 120 well-known open-source licenses. Niche, custom, or proprietary licenses produce "Unknown" compatibility verdicts. Use `[tool.license-audit.overrides]` to manually assign SPDX identifiers when detection fails.

- **OSADL is strict.** The matrix encodes a conservative reading of license compatibility. For weak-copyleft licenses (LGPL, MPL) it typically excludes permissive outbound licenses even though dynamic linking or unmodified redistribution can make those combinations acceptable in practice. Treat the matrix as the default guardrail and consult legal review for edge cases.

- **License string normalization.** PyPI packages use wildly inconsistent license strings. license-audit maps 60+ common aliases to SPDX identifiers, but uncommon or malformed strings may not be recognized and will be reported as UNKNOWN. Overrides can fill these gaps.

- **`requirements.txt` is flat.** When analyzing a `requirements.txt`, only direct dependencies listed in the file are parsed. Transitive dependencies are resolved by installing into a temporary environment, but the initial spec list comes from the file as written.

- **`uv.lock` format stability.** `uv.lock` has no formal specification. The parser supports version 1 of the lock format and fails explicitly on unrecognized versions.

- **Environment markers.** Dependency markers (platform, Python version, extras) are evaluated against the current runtime environment. Dependencies conditional on a different platform or Python version will not be included.

- **uv required for temp environments.** When analyzing a dependency file or project directory (rather than a venv or the current environment), license-audit creates a temporary environment using uv. If uv is not installed, these targets will fail. Direct venv and current-environment analysis do not require uv.

- **No legal advice.** license-audit provides informational analysis based on OSADL compatibility data. It is not a substitute for legal review. License compatibility can depend on distribution method, linking type, and jurisdiction - factors this tool does not evaluate.
