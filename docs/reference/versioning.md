# Versioning and stability

license-audit follows [Semantic Versioning](https://semver.org). From 1.0 on, a breaking change to any of these bumps the major version:

- **Commands and flags**: command names, options, and what they do.
- **`check` exit codes**: `0` all clear, `1` a policy violation or a check that could not run, `2` unknown licenses and nothing else.
- **Configuration**: the `[tool.license-audit]` keys, the values they accept, and what they mean.
- **The JSON report**, which also carries its own `schema_version`; see the [JSON report schema](report-schema.md#versioning-and-stability).

These can change in any release:

- **Human-readable output**: terminal output and the Markdown and notices reports are written for people. Parse the JSON report instead.
- **Results**: alias tables, built-in classifications, compatibility rules, and the OSADL data (which `license-audit refresh` also updates) improve over time, so a package's detected license or category, and therefore a `check` outcome, can change between releases. Pin license-audit where a CI run must be reproducible.
- **The Python API**: the command line is the public interface. The modules behind it are internal and can change in any release.
