# How it works

The pipeline runs in six steps:

1. **Read**: enumerate the installed packages in the target environment's site-packages and walk each package's `Requires-Dist` to build the dependency tree.
2. **Detect**: read each package's installed `*.dist-info/METADATA`. Licenses come from user overrides (normalized to canonical SPDX and validated at config load), or from PEP 639 `License-Expression`, which is authoritative when present. Otherwise the legacy `License` field and trove classifiers are consulted, and the first with a recognized license wins. Strings are normalized against the full SPDX license list, so any valid SPDX expression is kept intact; a declared license that can't be normalized is preserved verbatim (rather than discarded) so the report shows the actual string.
3. **Classify**: categorize each license as permissive, weak-copyleft, strong-copyleft, network-copyleft, or proprietary using OSADL copyleft data. A valid SPDX license that data doesn't cover reports as unknown until you classify it.
4. **Analyze**: check pairwise compatibility using the OSADL matrix and flag conflicts. Dependencies count as separate libraries: a permissive or weak-copyleft one never constrains a permissive or weak-copyleft outbound license, while a strong- or network-copyleft one needs a copyleft outbound license that the matrix allows for every dependency (see [Limitations](limitations.md#compatibility-reads-osadl-for-libraries)).
5. **Recommend**: determine the most permissive outbound license that satisfies every dependency constraint. A dual-licensed dependency (`MIT OR GPL-2.0`) can be used under any one of its alternatives, so an outbound license that satisfies any of them is accepted, here and in the conflict check. Its category, which the policy check uses, comes from its most permissive alternative.
6. **Report**: render findings as terminal output, Markdown, JSON, or third-party notices.

Because license-audit reads an already-installed environment, you provision it however you like first (`uv sync`, `poetry install`, `pip install -e .`). Whatever is installed is what gets audited, so choosing dependency groups is just a matter of how you provision.
