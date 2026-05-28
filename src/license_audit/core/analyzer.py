"""Top-level license audit pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from license_audit.config import LicenseAuditConfig, get_project_name, load_config
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.compatibility import CompatibilityMatrix
from license_audit.core.models import (
    UNKNOWN_LICENSE,
    AnalysisReport,
    LicenseCategory,
    PackageLicense,
)
from license_audit.core.policy import PolicyEngine
from license_audit.core.recommender import LicenseRecommender
from license_audit.environment.analyze import analyze_environment
from license_audit.environment.venv import (
    current_reader,
    is_venv_dir,
    reader_for_venv,
)
from license_audit.licenses.expression import ExpressionEvaluator
from license_audit.licenses.spdx import SpdxNormalizer
from license_audit.util import MetadataReader, canonicalize


@dataclass
class TargetInfo:
    """Resolved --target: which virtualenv to audit and where config lives."""

    site_packages: Path | None = None
    config_dir: Path | None = None


class TargetResolver:
    """Classifies a --target path as a virtualenv or a project directory."""

    def resolve(self, target: Path | None) -> TargetInfo:
        """Resolve `target` into a TargetInfo.

        Raises FileNotFoundError if `target` points nowhere or to a
        project without a virtualenv, or ValueError for a file target.
        """
        if target is None:
            cwd = Path.cwd()
            venv = cwd / ".venv"
            if is_venv_dir(venv):
                return TargetInfo(site_packages=venv, config_dir=cwd)
            return TargetInfo(config_dir=cwd)

        resolved = target.resolve()

        if resolved.is_file():
            msg = (
                f"{resolved} is a file. license-audit reads an installed "
                "environment: pass a project directory or a virtualenv, or "
                "run inside your provisioned environment."
            )
            raise ValueError(msg)

        if is_venv_dir(resolved):
            return TargetInfo(site_packages=resolved, config_dir=resolved.parent)

        if resolved.is_dir():
            return self._detect_in_project_dir(resolved)

        msg = f"Target not found: {resolved}"
        raise FileNotFoundError(msg)

    @staticmethod
    def _detect_in_project_dir(project_dir: Path) -> TargetInfo:
        venv = project_dir / ".venv"
        if is_venv_dir(venv):
            return TargetInfo(site_packages=venv, config_dir=project_dir)

        msg = (
            f"No virtualenv found in {project_dir}. Provision one first "
            "(e.g. `uv sync`) and re-run, or pass --target <venv>."
        )
        raise FileNotFoundError(msg)


class LicenseAuditor:
    """Runs the full audit pipeline and returns an AnalysisReport.

    Each collaborator is injectable so tests can swap pieces, but a plain
    `LicenseAuditor().run(target=Path('.'))` works without any setup.
    """

    def __init__(
        self,
        resolver: TargetResolver | None = None,
        classifier: LicenseClassifier | None = None,
        matrix: CompatibilityMatrix | None = None,
        normalizer: SpdxNormalizer | None = None,
        recommender: LicenseRecommender | None = None,
        policy: PolicyEngine | None = None,
        expression: ExpressionEvaluator | None = None,
    ) -> None:
        self._matrix = matrix or CompatibilityMatrix()
        self._classifier = classifier or LicenseClassifier()
        self._normalizer = normalizer or SpdxNormalizer(matrix=self._matrix)
        self._expression = expression or ExpressionEvaluator(
            classifier=self._classifier,
            normalizer=self._normalizer,
        )
        self._recommender = recommender or LicenseRecommender(
            matrix=self._matrix,
            classifier=self._classifier,
            normalizer=self._normalizer,
        )
        self._policy = policy or PolicyEngine(
            classifier=self._classifier,
            normalizer=self._normalizer,
            expression=self._expression,
        )
        self._resolver = resolver or TargetResolver()

    def run(
        self,
        target: Path | None = None,
        config: LicenseAuditConfig | None = None,
        config_dir: Path | None = None,
    ) -> AnalysisReport:
        """Run the audit pipeline against `target` and return the report.

        `config_dir` overrides where config and the project name are read
        from; it defaults to the target's location.
        """
        info = self._resolver.resolve(target)
        effective_dir = config_dir or info.config_dir

        if config is None:
            config = load_config(effective_dir)
        project_name = get_project_name(effective_dir)

        reader = self._reader_for(info)
        tree = analyze_environment(project_name, reader, dict(config.overrides))
        packages = tree.flatten()
        self._classify_packages(packages)
        self._collect_license_text(packages, reader)
        self._apply_ignores(packages, config.ignored_packages)

        dep_packages = [p for p in packages if p.name != canonicalize(project_name)]
        active_packages = [p for p in dep_packages if not p.ignored]
        dep_licenses = [p.license_expression for p in active_packages]
        dep_spdx_ids = self._extract_spdx_ids(dep_licenses)

        has_unknown = any(
            p.category == LicenseCategory.UNKNOWN for p in active_packages
        )
        recommended = [] if has_unknown else self._recommender.recommend(dep_licenses)
        incompatible = self._matrix.find_incompatible_pairs(dep_spdx_ids)
        action_items = self._policy.build_action_items(
            dep_packages,
            incompatible,
            config,
        )
        policy_passed = self._policy.check(
            dep_packages,
            self._policy.build_policy(config),
        )

        return AnalysisReport(
            project_name=project_name,
            source=self._describe_source(info),
            packages=dep_packages,
            incompatible_pairs=incompatible,
            recommended_licenses=recommended,
            action_items=action_items,
            policy_passed=policy_passed,
        )

    @staticmethod
    def _reader_for(info: TargetInfo) -> MetadataReader:
        if info.site_packages is not None:
            return reader_for_venv(info.site_packages)
        return current_reader()

    @staticmethod
    def _describe_source(info: TargetInfo) -> str:
        if info.site_packages is not None:
            return str(info.site_packages)
        return "active environment"

    def _classify_packages(self, packages: list[PackageLicense]) -> None:
        for pkg in packages:
            if pkg.license_expression != UNKNOWN_LICENSE:
                self._classify_package(pkg)

    def _classify_package(self, pkg: PackageLicense) -> None:
        pkg.category = self._expression.classify(pkg.license_expression)

    @staticmethod
    def _collect_license_text(
        packages: list[PackageLicense],
        reader: MetadataReader,
    ) -> None:
        for pkg in packages:
            pkg.license_text = reader.read_license_text(pkg.name)

    def _apply_ignores(
        self,
        packages: list[PackageLicense],
        ignored_packages: dict[str, str],
    ) -> None:
        """Mark packages listed in config.ignored_packages as ignored."""
        if not ignored_packages:
            return
        reasons = {
            canonicalize(name): reason for name, reason in ignored_packages.items()
        }
        for pkg in packages:
            reason = reasons.get(pkg.name)
            if reason is not None:
                pkg.ignored = True
                pkg.ignore_reason = reason

    def _extract_spdx_ids(self, expressions: list[str]) -> list[str]:
        ids: set[str] = set()
        for expr in expressions:
            if expr != UNKNOWN_LICENSE:
                for lic in self._expression.required_ids(expr):
                    ids.add(lic)
        return list(ids)
