# Comparison with other tools

| Capability | license-audit | [ScanCode](https://github.com/nexB/scancode-toolkit) | [pip-licenses](https://github.com/raimon49/pip-licenses) | [liccheck](https://github.com/dhatim/python-liccheck) |
|---|---|---|---|---|
| License detection from package metadata | Yes | No (file-level) | Yes | Yes |
| File-level license scanning | No | Yes | No | No |
| Pairwise compatibility analysis (OSADL) | Yes | No | No | No |
| Outbound license recommendation | Yes | No | No | No |
| Transitive dependency tree with parents | Yes | N/A | No | No |
| Dual-license resolution (OR expressions) | Yes (picks most permissive) | N/A | No | No |
| CI policy gating with exit codes | Yes | Via scripting | Via flags | Yes |
| Compliance report generation | Markdown, JSON, notices | JSON, HTML, CSV, SPDX | CSV, JSON, Markdown | No |
| Allow/deny lists | Yes | Via scripting | No | Yes |
| Dependency group filtering | Yes (main, dev, optional, PEP 735) | N/A | No | No |
| Language support | Python | Any | Python | Python |
| `pyproject.toml` configuration | Yes | No | No | Yes |
| uv / PEP 639 support | Yes | No | No | No |

**In short:** license-audit is for Python teams that want actionable compliance guidance - not just "what licenses do I have?" but "what can I ship, and do my dependencies conflict?" If you need file-level scanning across a polyglot codebase, ScanCode is the right tool for that job and complements license-audit well.
