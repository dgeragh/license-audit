"""Third-party notices renderer, bundles license texts into a single file."""

from __future__ import annotations

from license_audit.core.models import AnalysisReport, PackageLicense
from license_audit.reports._format import (
    attribution_footer,
    fenced_code_block,
    generated_metadata_block,
    license_label,
)


class NoticesRenderer:
    """Render a THIRD_PARTY_NOTICES document with full license texts."""

    def render(self, report: AnalysisReport) -> str:
        """Render the report as a third-party notices document."""
        sections = [self._header(report)]

        for pkg in sorted(report.packages, key=lambda p: p.name):
            sections.append(self._package_section(pkg))

        sections.append(self._footer())
        return "\n".join(sections)

    def _header(self, report: AnalysisReport) -> str:
        return (
            f"# Third-Party Notices\n\n"
            f"This file contains the licenses and copyright notices for "
            f"third-party software used by **{report.project_name}**.\n\n"
            f"{generated_metadata_block(report)}"
        )

    def _package_section(self, pkg: PackageLicense) -> str:
        lines = [
            f"\n---\n\n## {pkg.name} {pkg.version}\n",
            f"- **License:** {license_label(pkg.display_license)}",
            f"- **Category:** {pkg.category.value}",
        ]
        if pkg.declared_license:
            lines.append(
                "- *Declared license string; not a recognized SPDX identifier.*"
            )

        # Prefer a bundled LICENSE file; fall back to the declared string itself
        # so packages that only put their terms in the metadata aren't blank.
        text = pkg.license_text or pkg.declared_license
        if text:
            lines.append(f"\n{fenced_code_block(text)}\n")
        else:
            lines.append(
                "\n*License text not available. "
                "Refer to the package distribution for the full license.*\n"
            )

        return "\n".join(lines)

    def _footer(self) -> str:
        return attribution_footer(
            "This file is for attribution and compliance purposes. "
            "It does not constitute legal advice.",
        )
