# JSON report schema

`license-audit analyze --format json` and `license-audit report --format json` emit the same JSON document, described here. A machine-readable [JSON Schema](report-schema.json) generated from the underlying model is published alongside this page.

## Versioning and stability

The document carries a `schema_version` field, currently `1`. It is bumped only on breaking changes:

- removing or renaming a field
- changing a field's type, nullability, or meaning
- removing or renaming an enum value

Additive changes do not bump the version and are announced in the changelog: new fields and new enum values may appear at any release. Consumers should ignore unknown fields and tolerate unrecognized enum values.

`tool_version` is informational and records the license-audit version that produced the report.

## Top-level fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Always `1` for this schema version |
| `tool_version` | string | Version of license-audit that produced the report |
| `project_name` | string | Name of the audited project, empty if unknown |
| `source` | string | Human-readable description of the audit target |
| `packages` | array of [PackageLicense](#packagelicense) | One entry per audited package |
| `incompatible_pairs` | array of [CompatibilityResult](#compatibilityresult) | License pairs found incompatible |
| `recommended_licenses` | array of string | Recommended outbound licenses as SPDX ids, most permissive first |
| `action_items` | array of [ActionItem](#actionitem) | Follow-ups the user should address |
| `policy_passed` | boolean or null | Policy gate result, `null` when no policy is configured |

## PackageLicense

| Field | Type | Description |
|---|---|---|
| `name` | string | Package name |
| `version` | string | Installed package version |
| `license_expression` | string | Canonical SPDX expression, `UNKNOWN` when not detected |
| `declared_license` | string or null | Raw license string as declared by the package, `null` when nothing was declared |
| `license_source` | string | How the license was detected, see [LicenseSource](#licensesource) |
| `category` | string | Copyleft classification, see [LicenseCategory](#licensecategory) |
| `category_overridden` | boolean | Whether the category came from a configuration override |
| `parent` | string | Top-level dependency that pulls this package in |
| `license_text` | string or null | Full license text when available |
| `ignored` | boolean | Whether the package is excluded from policy evaluation |
| `ignore_reason` | string | Reason given for ignoring, empty otherwise |

A package whose license could not be mapped to SPDX keeps its raw string in `declared_license` with `license_expression` set to `UNKNOWN`; a package with no license metadata at all has `declared_license` set to `null`.

## CompatibilityResult

| Field | Type | Description |
|---|---|---|
| `inbound` | string | License of the dependency |
| `outbound` | string | License it was checked against |
| `verdict` | string | Compatibility verdict, see [Verdict](#verdict) |

## ActionItem

| Field | Type | Description |
|---|---|---|
| `severity` | string | `warning` or `error` |
| `package` | string | Package the item concerns, empty for project-wide items |
| `message` | string | What to do |

## Enum values

### LicenseCategory

`permissive`, `weak-copyleft`, `strong-copyleft`, `network-copyleft`, `proprietary`, `unknown`

### LicenseSource

`pep639`, `metadata`, `classifier`, `override`, `unknown`

### Verdict

`compatible`, `incompatible`, `unknown`, `check-dependency`, `same`
