# Changelog

## 0.11.0 (2026-07-02)

### Fixed

- License classifications now apply to components of an expression containing a license outside the OSADL data (classifying `CNRI-Python` in `Apache-2.0 AND CNRI-Python` was ignored and warned as a typo)
- Deprecated SPDX ids inside compound expressions now map to their modern forms (`GPL-2.0+ AND MIT` reads `GPL-2.0-or-later AND MIT`)
- The Markdown report's Licenses Requiring Review section shows the SPDX expression for an unclassified license instead of "not detected"
- A denied base license now also blocks its `WITH exception` forms (denying `GPL-2.0-only` catches `GPL-2.0-only WITH Classpath-exception-2.0`)
- Compatibility analysis resolves `OR` expressions to the same branch as classification when a component is deemed by `license-classifications`, so conflicts on the chosen branch are no longer hidden
- A `license-classifications` key written as a full compound expression now drops its components from compatibility analysis, matching component keys
- A license string that isn't parseable no longer triggers a false denied-license violation when a denylist is configured; it is matched whole against the lists instead
- A direct dependency that another direct dependency also requires is reported as direct instead of transitive

### Changed

- License strings are validated against the full SPDX license list: any valid SPDX expression is preserved instead of collapsing to `UNKNOWN`, is checked against allowed/denied lists, and displays in canonical form
- `WITH` expressions survive normalization; a `X WITH Y` clause classifies as a single component keyed by its full text
- The action item for a license without classification data now suggests `license-classifications` instead of calling the license unrecognized
- `check`, `recommend`, and report messages say "unclassified" rather than "undetected" or "unrecognized", and the withheld-recommendation explanation no longer claims a classified license has no SPDX id

## 0.10.0 (2026-06-29)

### Fixed

- License `overrides` keyed by a PyPI-style name with hyphens or dots now apply
- Dependencies declared in metadata but absent from the audited environment are no longer reported as phantom unknown packages
- Packages installed as `.egg-info` (legacy `setup.py` installs), and dist-info directories whose name part contains hyphens, are now detected
- `check` now reports the package and license that fall outside `allowed-licenses`
- Ignore reasons containing `|` or a newline no longer break the Markdown Ignored Packages table
- A malformed `pyproject.toml` now reports a clear error instead of a traceback
- `refresh` writes cache files atomically so an interrupted download can't leave a half-written file behind
- Report summaries count each package once: ignored packages are no longer also tallied as copyleft or unknown, and proprietary packages have their own count
- The Markdown report omits the policy line when no policy was evaluated instead of showing a misleading `FAILED`
- `Source` paths containing square brackets now render correctly in terminal output
- JSON reports written with `--output` end with a trailing newline

### Changed

- Unknown keys in `[tool.license-audit]` are now rejected rather than silently ignored

## 0.9.0 (2026-05-28)

### Added

- Unrecognized licenses now show their actual declared identifier instead of `UNKNOWN`, distinguish undetected from unrecognized, and include their license text in Markdown reports for review
- License classification via `[tool.license-audit.license-classifications]`: deem a license a category and have it apply to every package that uses it, including individual components of `AND`/`OR` expressions

### Changed

- Audits a user-provisioned environment directly; removed built-in provisioning and lockfile parsing (`uv.lock`, `poetry.lock`, `pixi.lock`, `requirements.txt`, `pyproject.toml`)

## 0.8.0 (2026-05-27)

### Fixed

- Forward custom package indices to `pip wheel`

### Changed

- Bumped `urllib3`, `idna`, and `pymdown-extensions` via Dependabot

## 0.7.0 (2026-05-06)

### Changed

- Dropped `uv` as a runtime requirement; temp environment provisioning now uses `pip wheel`
- Recommended outbound licenses prefer a curated shortlist (MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause) before falling back to alphabetical
- Wider severity gradient on the dependency table; unknown licenses move from dim to bright red

### Added

- Progress spinner during provisioning
- Windows and macOS in the CI matrix
- Documentation for the `recommend` and `refresh` commands
- AND-expression action items name the unrecognized component(s) instead of the whole expression

### Fixed

- `recommend` no longer suggests permissive licenses when an unknown-category dependency is present
- Ignored packages no longer drive the "most restrictive dependency" line in `recommend`
- Unknown summary count now includes packages whose category resolves to unknown
- Brackets in user-supplied ignore reasons and license overrides render correctly in the terminal

## 0.6.0 (2026-05-05)

### Fixed

- AND expression evaluation now requires compliance with every component

## 0.5.0 (2026-05-04)

### Added

- `target` field in `[tool.license-audit]` to set a default `--target`
- Target source reporting for CLI command outputs

### Fixed

- Encoding errors when running on systems with a non-UTF-8 default locale

## 0.4.0 (2026-04-26)

### Added

- Support for Poetry projects via `poetry.lock`
- Support for Pixi projects via `pixi.lock`
- Integration test suite covering end-to-end analyzer flows and CLI subprocess execution

## 0.3.0 (2026-04-19)

### Added

- `[tool.license-audit.ignored-packages]` configuration for exempting specific packages from policy evaluation

## 0.2.0 (2026-04-17)

### Added

- Reference documentation pages covering tool comparison, how detection works, and known limitations

### Changed

- Improved terminal rendering for `recommend`, `check`, and `report` commands with clearer formatting and shared layout helpers
- Streamlined README and user guide, including an expanded CI integration guide
- Internal refactor of the analyzer, policy engine, classifier, data store, SPDX normalizer, recommender, sources, and environment provisioning into class-based implementations (no change to CLI behavior or output contracts)

## 0.1.1 (2026-04-13)

### Added

- License detection for all transitive dependencies using PEP 639 metadata, trove classifiers, and configurable overrides
- Pairwise compatibility analysis using the OSADL compatibility matrix (123 licenses)
- License recommendations based on dependency constraints
- Compliance report generation in Markdown, JSON, and third-party notices formats
- Policy checks with configurable levels (`permissive`, `weak-copyleft`, `strong-copyleft`, `network-copyleft`)
- Dependency group filtering (`main`, `dev`, `optional:<name>`, `group:<name>`) to scope analysis to specific groups
- SPDX normalization with 50+ common PyPI license string aliases
- Support for `uv.lock`, `pyproject.toml`, `requirements.txt`, and live virtual environments
- Refreshable OSADL data via `license-audit refresh`
- Configuration via `[tool.license-audit]` in `pyproject.toml`
