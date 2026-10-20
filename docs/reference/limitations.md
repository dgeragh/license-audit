# Limitations

## Detection is package-level

license-audit reads what's declared in package metadata: PEP 639 fields, the legacy `License` field, trove classifiers. It does not scan the contents of `LICENSE` or `NOTICE` files to identify a license, and it can't detect bundled or vendored code whose license differs from the package's declaration. For file-level scanning, use [ScanCode](https://github.com/nexB/scancode-toolkit).

## OSADL coverage is finite

The OSADL compatibility matrix covers about 120 well-known open-source licenses. A handful of common permissive licenses its data leaves out are classified built-in: CC0-1.0, CNRI-Python, ZPL-2.1, CC-BY-4.0, Python-2.0.1, MIT-Modern-Variant, and BSD-3-Clause-Clear. Any other valid SPDX license outside the data is detected but classifies as unknown; record your judgement in `[tool.license-audit.license-classifications]` to resolve it (an entry there also overrides a built-in category). Strings that aren't SPDX at all produce "Unknown" verdicts; use `[tool.license-audit.overrides]` to assign SPDX identifiers manually when detection fails.

## Compatibility reads OSADL for libraries

The OSADL matrix answers whether code under one license can be incorporated into a work under another. license-audit applies it the way Python dependencies are combined, as separately distributed libraries:

- A permissive or weak-copyleft dependency (MIT, LGPL, MPL) never constrains a permissive or weak-copyleft outbound license, because its obligations stay with its own files.
- A strong- or network-copyleft dependency (GPL, AGPL) makes the combined work copyleft, so it needs a strong- or network-copyleft outbound license, and every other dependency is held to the matrix verdict for that license.

One verdict departs from OSADL: PSF-2.0 (typing-extensions, among others) counts as usable in GPL-family works, as the FSF's license list states, where OSADL says it is not. The matrix is otherwise a strict reading of compatibility, so treat its conflicts as a default guardrail, not a final answer.

## License strings on PyPI are messy

PyPI packages use inconsistent license strings. license-audit normalizes 60+ common aliases to SPDX identifiers. Strings it can't map (e.g. `Proprietary License`) are reported verbatim and flagged as an unknown category rather than collapsed to `UNKNOWN`, and the Markdown report's **Licenses Requiring Review** section includes their license text so you can verify the terms. Use overrides to assign a canonical SPDX identifier once you've confirmed it.

## You must provision the environment first

license-audit reads an already-installed environment; it does not resolve or install dependencies. Run `uv sync`, `poetry install`, `pip install -e .`, or equivalent before auditing. Only what's installed is audited, so a partial install yields a partial audit.

## Environment markers track the host

Dependency markers (platform, Python version, extras) are evaluated against the current runtime. Dependencies that are conditional on a different platform or Python version aren't included.

## Not legal advice

The output is informational, based on OSADL data. Real license compatibility depends on how you distribute, how you link, and what jurisdiction you're in. Treat anything this tool generates as a starting point for legal review, not the final answer.
