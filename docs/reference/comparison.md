# Comparison with other tools

| Capability | license-audit | [ScanCode](https://github.com/nexB/scancode-toolkit) | [pip-licenses](https://github.com/raimon49/pip-licenses) | [liccheck](https://github.com/dhatim/python-license-check) |
|---|---|---|---|---|
| License detection from package metadata | Yes | No (file-level) | Yes | Yes |
| File-level license scanning | No | Yes | No | No |
| Pairwise compatibility analysis (OSADL) | Yes | No | No | No |
| Outbound license recommendation | Yes | No | No | No |
| Transitive dependency tree with parents | Yes | N/A | No | Chain for flagged packages |
| Dual-license resolution (OR expressions) | Yes (any alternative) | N/A | No | Per strategy level |
| CI policy gating with exit codes | Yes | Via scripting | Via flags | Yes |
| Compliance report generation | Markdown, JSON, notices | JSON, HTML, CSV, SPDX | Markdown, reST, HTML, JSON, CSV, and more | Text report |
| Allow/deny lists | Yes | Via scripting | Yes | Yes |
| Dependency group filtering | Via provisioning | N/A | No | Extras via config |
| Language support | Python | Any | Python | Python |
| `pyproject.toml` configuration | Yes | No | Yes | Yes |
| Audits any installed environment (uv, Poetry, pip) | Yes | No | Yes | Yes |
| PEP 639 `License-Expression` | Yes | No | Yes | No |

license-audit flags dependency conflicts and provides licensing recommendations. If you need file-level scanning across a multi-language codebase, use ScanCode.
