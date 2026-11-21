# JSON report schema

`license-audit analyze --format json` and `license-audit report --format json` emit the same JSON document, described here. A machine-readable [JSON Schema](report-schema.json) generated from the underlying model is published alongside this page.

## Versioning and stability

The document carries a `schema_version` field, currently `2`. It is bumped only on breaking changes:

- removing or renaming a field
- changing a field's type, nullability, or meaning
- removing or renaming an enum value

Additive changes do not bump the version and are announced in the changelog: new fields and new enum values may appear at any release. Consumers should ignore unknown fields and tolerate unrecognized enum values.

Version history:

- **2**: entries in `incompatible_pairs` name their licenses `license_a`/`license_b` instead of `inbound`/`outbound` (both are dependency licenses; the old names wrongly suggested one was an outbound license), and the always-`incompatible` `verdict` field was removed.
- **1**: initial versioned schema.

`tool_version` is informational and records the license-audit version that produced the report.

## Top-level fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Always `2` for this schema version |
| `tool_version` | string | Version of license-audit that produced the report |
| `project_name` | string | Name of the audited project from `pyproject.toml` (`[project]`, else `[tool.poetry]`) or the package installed from the project's directory, the literal string `unknown` when it can't be determined |
| `source` | string | Human-readable description of the audit target, naming the environment by path |
| `osadl_data` | [OsadlData](#osadldata) or null | The OSADL compatibility data the audit used. Always set by current versions; `null` is reserved |
| `packages` | array of [PackageLicense](#packagelicense) | One entry per audited package |
| `missing_dependencies` | array of string | Packages the project requires that aren't installed in the audited environment, so their licenses weren't checked (see [required dependencies](../user-guide/configuration.md#required-dependencies)). Any entry fails the policy and withholds recommendations |
| `incompatible_pairs` | array of [IncompatiblePair](#incompatiblepair) | License pairs found incompatible |
| `incompatible_groups` | array of [IncompatibleGroup](#incompatiblegroup) | Licenses no outbound license satisfies together although every pair of them can, reported when no incompatible pair explains the conflict |
| `recommended_licenses` | array of string | Recommended outbound licenses as SPDX ids, most permissive first |
| `review_licenses` | array of string | When no outbound license is a definite fit, the ones that satisfy every dependency once you confirm how they are combined (OSADL's "Check dependency" verdict), most permissive first; empty otherwise. Unless recommendations are withheld, exactly one of `recommended_licenses`, `review_licenses`, and the incompatible pairs and groups is non-empty |
| `action_items` | array of [ActionItem](#actionitem) | Follow-ups the user should address |
| `policy_passed` | boolean or null | Policy gate result, the same verdict `check` reaches: `false` on an incompatible pair or group, a missing required dependency, a policy violation, or an unknown license while `fail-on-unknown` is on. Always set by current versions; `null` is reserved |

## OsadlData

| Field | Type | Description |
|---|---|---|
| `origin` | string | `bundled` for the data shipped with license-audit, `refreshed` for the copy `license-audit refresh` saved; an audit uses whichever is newer |
| `timestamp` | string | When OSADL published the data, as recorded in it (`2026-02-12T16:31:00+0000`) |

## PackageLicense

| Field | Type | Description |
|---|---|---|
| `name` | string | Package name |
| `version` | string | Installed package version |
| `license_expression` | string | Canonical SPDX expression, `UNKNOWN` when not detected |
| `declared_license` | string or null | Raw license string as declared by the package, `null` when nothing was declared |
| `license_source` | string | How the license was detected, see [LicenseSource](#licensesource) |
| `category` | string | Copyleft classification, see [LicenseCategory](#licensecategory) |
| `category_overridden` | boolean | Whether the category came from a `license-classifications` entry: one for the whole license, or for a component that decides a compound license's category (an `overrides` entry sets `license_source` instead) |
| `parent` | string | Top-level dependency that pulls this package in; equal to `name` for a direct dependency: one the project declares, or an installed package nothing else requires |
| `license_text` | string or null | Full license text when available |
| `ignored` | boolean | Whether the package is excluded from policy evaluation |
| `ignore_reason` | string | Reason given for ignoring, empty otherwise |

A package whose license could not be mapped to SPDX keeps its raw string in `declared_license` with `license_expression` set to `UNKNOWN`; a package with no license metadata at all has `declared_license` set to `null`.

## IncompatiblePair

| Field | Type | Description |
|---|---|---|
| `license_a` | string | One dependency license of the conflicting pair |
| `license_b` | string | The other dependency license |

The pair is unordered: `license_a`/`license_b` carry no meaning beyond which license was encountered first. A dual-licensed dependency whose every alternative conflicts is named by its full OR expression.

## IncompatibleGroup

| Field | Type | Description |
|---|---|---|
| `licenses` | array of string | Dependency licenses no outbound license satisfies together. Removing any one of them leaves a combination some outbound license satisfies |

A group of one is a dual-licensed dependency none of whose alternatives any outbound license satisfies.

## ActionItem

| Field | Type | Description |
|---|---|---|
| `code` | string | What the item is about, see [ActionCode](#actioncode). Stable across releases, unlike `message` |
| `severity` | string | `warning` or `error` |
| `package` | string | Package the item concerns, empty for project-wide items |
| `message` | string | What to do |

## Enum values

### LicenseCategory

`permissive`, `weak-copyleft`, `strong-copyleft`, `network-copyleft`, `proprietary`, `unknown`

### ActionCode

| Value | Severity | Raised when |
|---|---|---|
| `missing-dependencies` | `error` | Dependencies the project requires aren't installed in the audited environment |
| `unknown-license` | `warning` | A package's license can't be detected or classified |
| `incompatible-licenses` | `error` | Two dependency licenses share no outbound license |
| `incompatible-group` | `error` | Licenses no outbound license satisfies together, though every pair can |
| `denied-license` | `error` | A package uses a license in `denied-licenses` |
| `license-not-allowed` | `error` | A package's license isn't in `allowed-licenses` |
| `policy-exceeded` | `error` | A package's category is above the `policy` level |
| `copyleft-dependency` | `warning` | A strong- or network-copyleft dependency the policy allows |
| `review-licenses` | `warning` | Only outbound licenses OSADL marks "Check dependency" fit every dependency |
| `unmatched-classification` | `warning` | A `license-classifications` entry matches no package |
| `unmapped-classifier` | `warning` | A license classifier can't be mapped, beside ones that can |
| `dropped-license-terms` | `warning` | A license read from classifiers drops terms its License field states |
| `mixed-classifiers` | `warning` | License classifiers in different categories are read as a choice between them |

### LicenseSource

`pep639`, `metadata`, `classifier`, `override`, `unknown`
