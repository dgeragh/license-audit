# How it works

The pipeline runs in six steps:

1. **Read**: enumerate the installed packages in the target environment's site-packages and walk each package's `Requires-Dist` to build the dependency tree.
2. **Detect**: read each package's installed `*.dist-info/METADATA`. Licenses come from PEP 639 `License-Expression`, the legacy `License` field, trove classifiers, or user overrides.
3. **Classify**: categorize each license as permissive, weak-copyleft, strong-copyleft, or network-copyleft using OSADL copyleft data.
4. **Analyze**: check pairwise compatibility using the OSADL matrix and flag conflicts.
5. **Recommend**: determine the most permissive outbound license that satisfies every dependency constraint. For OR expressions (e.g. `MIT OR GPL-2.0`), the most permissive alternative is selected before constraint solving.
6. **Report**: render findings as terminal output, Markdown, JSON, or third-party notices.

Because license-audit reads an already-installed environment, you provision it however you like first (`uv sync`, `poetry install`, `pip install -e .`). Whatever is installed is what gets audited, so choosing dependency groups is just a matter of how you provision.
