"""Main analysis orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from license_audit.config import LicenseAuditConfig, get_project_name, load_config
from license_audit.core.classifier import LicenseClassifier
from license_audit.core.compatibility import CompatibilityMatrix
from license_audit.core.models import (
    CATEGORY_RANK,
    UNKNOWN_LICENSE,
    ActionItem,
    AnalysisReport,
    CompatibilityResult,
    LicenseCategory,
    LicensePolicy,
    PackageLicense,
    PolicyLevel,
)
from license_audit.core.recommender import recommend_licenses
from license_audit.environment.analyze import (
    analyze_environment,
    analyze_installed_packages,
)
from license_audit.environment.provision import (
    ProvisionedEnv,
    is_venv_dir,
    provision_current_env,
    provision_from_venv,
    provision_temp_env,
)
from license_audit.licenses.spdx import get_simple_licenses
from license_audit.sources.base import PackageSpec, Source
from license_audit.sources.pyproject import PyprojectSource
from license_audit.sources.requirements import RequirementsSource
from license_audit.sources.uv_lock import UvLockSource
from license_audit.util import canonicalize, get_license_text

_classifier = LicenseClassifier()
_matrix = CompatibilityMatrix()

_POLICY_MAX_RANK: dict[PolicyLevel, int] = {
    PolicyLevel.PERMISSIVE: CATEGORY_RANK[LicenseCategory.PERMISSIVE],
    PolicyLevel.WEAK_COPYLEFT: CATEGORY_RANK[LicenseCategory.WEAK_COPYLEFT],
    PolicyLevel.STRONG_COPYLEFT: CATEGORY_RANK[LicenseCategory.STRONG_COPYLEFT],
    PolicyLevel.NETWORK_COPYLEFT: CATEGORY_RANK[LicenseCategory.NETWORK_COPYLEFT],
}


@dataclass
class _TargetInfo:
    """Result of resolving a --target argument."""

    source_path: Path | None = None
    site_packages: Path | None = None
    config_dir: Path | None = None


def analyze(
    target: Path | None = None,
    config: LicenseAuditConfig | None = None,
) -> AnalysisReport:
    """Run a full license analysis.

    Args:
        target: Path to a project dir, dependency file, or venv.
            None means analyze the current environment.
        config: Optional pre-loaded config (loads from pyproject.toml if None).

    Returns:
        A complete AnalysisReport.
    """
    info = _resolve_target(target)

    if config is None:
        config = load_config(info.config_dir)

    project_name = get_project_name(info.config_dir)
    overrides = dict(config.overrides)

    # dependency_groups requires a source file to filter; it can't work
    # when analyzing a live environment directly.
    if (
        config.dependency_groups
        and info.source_path is None
        and info.site_packages is None
    ):
        import warnings

        warnings.warn(
            "--dependency-groups has no effect without --target. "
            "Specify a project directory or dependency file to enable group filtering.",
            UserWarning,
            stacklevel=2,
        )

    # Build source after config is loaded so dependency_groups is available
    source: Source | None = None
    if info.source_path is not None:
        source = _create_source(info.source_path, config.dependency_groups)

    # Provision environment and analyze
    specs: list[PackageSpec] | None = None
    env: ProvisionedEnv
    if info.site_packages is not None:
        env = provision_from_venv(info.site_packages)
    elif source is not None:
        specs = source.parse()
        env = provision_temp_env(specs)
    else:
        env = provision_current_env()

    with env:
        if specs is not None:
            # Source-based: root project isn't installed, use known package list
            pkg_extras = {s.name: s.extras for s in specs if s.extras}
            tree = analyze_installed_packages(
                project_name,
                env.site_packages,
                [s.name for s in specs],
                overrides,
                pkg_extras,
            )
        else:
            # Venv or current env: root project may be installed
            tree = analyze_environment(project_name, env.site_packages, overrides)
        packages = tree.flatten()

        # Classify each package
        for pkg in packages:
            if pkg.license_expression != UNKNOWN_LICENSE:
                _classify_package(pkg)

        # Collect license texts while the environment is still available
        for pkg in packages:
            pkg.license_text = get_license_text(pkg.name, env.site_packages)

        # Skip the root project itself for analysis
        dep_packages = [p for p in packages if p.name != canonicalize(project_name)]

        # Collect license expressions
        dep_licenses = [p.license_expression for p in dep_packages]
        dep_spdx_ids = _extract_spdx_ids(dep_licenses)

        # Check compatibility
        recommended = recommend_licenses(dep_licenses)

        # Find incompatible pairs among dependencies
        incompatible = _matrix.find_incompatible_pairs(dep_spdx_ids)

        # Build action items
        action_items = _build_action_items(dep_packages, incompatible, config)

        # Apply policy
        policy = _build_policy(config)
        policy_passed = _check_policy(dep_packages, policy)

    return AnalysisReport(
        project_name=project_name,
        packages=dep_packages,
        incompatible_pairs=incompatible,
        recommended_licenses=recommended,
        action_items=action_items,
        policy_passed=policy_passed,
    )


def _resolve_target(target: Path | None) -> _TargetInfo:
    """Resolve a --target argument into source_path, site_packages, and config_dir."""
    if target is None:
        return _TargetInfo(config_dir=Path.cwd())

    target = target.resolve()

    # Target is a file - validate and store path
    if target.is_file():
        config_dir = target.parent
        _validate_source_file(target)
        return _TargetInfo(source_path=target, config_dir=config_dir)

    # Target is a venv directory (has site-packages, no pyproject.toml)
    if is_venv_dir(target):
        config_dir = target.parent
        return _TargetInfo(site_packages=target, config_dir=config_dir)

    # Target is a project directory - auto-detect source
    if target.is_dir():
        return _auto_detect_project(target)

    msg = f"Target not found: {target}"
    raise FileNotFoundError(msg)


def _validate_source_file(path: Path) -> None:
    """Validate that a file is a recognized dependency source."""
    name = path.name.lower()
    if name in ("uv.lock", "pyproject.toml"):
        return
    if name.startswith("requirements") and name.endswith(".txt"):
        return
    msg = f"Unrecognized dependency file: {path.name}"
    raise ValueError(msg)


def _create_source(path: Path, groups: list[str] | None = None) -> Source:
    """Instantiate the correct Source for a dependency file."""
    name = path.name.lower()
    if name == "uv.lock":
        return UvLockSource(path, groups=groups)
    if name.startswith("requirements") and name.endswith(".txt"):
        return RequirementsSource(path, groups=groups)
    if name == "pyproject.toml":
        return PyprojectSource(path, groups=groups)
    msg = f"Unrecognized dependency file: {path.name}"
    raise ValueError(msg)


def _auto_detect_project(project_dir: Path) -> _TargetInfo:
    """Auto-detect the best source in a project directory."""
    config_dir = project_dir

    # Try uv.lock first
    uv_lock = project_dir / "uv.lock"
    if uv_lock.exists():
        return _TargetInfo(source_path=uv_lock, config_dir=config_dir)

    # Try requirements.txt
    requirements = project_dir / "requirements.txt"
    if requirements.exists():
        return _TargetInfo(source_path=requirements, config_dir=config_dir)

    # Try pyproject.toml dependencies
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        return _TargetInfo(source_path=pyproject, config_dir=config_dir)

    # Fall back to the project's .venv if it exists
    venv = project_dir / ".venv"
    if venv.is_dir():
        return _TargetInfo(site_packages=venv, config_dir=config_dir)

    msg = (
        f"No dependency source found in {project_dir}. "
        "Expected uv.lock, requirements.txt, pyproject.toml, or .venv"
    )
    raise FileNotFoundError(msg)


def _classify_package(pkg: PackageLicense) -> None:
    """Classify a package's license category."""
    simple = get_simple_licenses(pkg.license_expression)
    if len(simple) == 1:
        pkg.category = _classifier.classify(simple[0])
    elif len(simple) > 1:
        categories = [_classifier.classify(s) for s in simple]
        # For OR expressions, pick the most permissive (lowest rank)
        most_permissive = min(categories, key=lambda c: CATEGORY_RANK.get(c, 5))
        pkg.category = most_permissive


def _extract_spdx_ids(expressions: list[str]) -> list[str]:
    """Extract unique SPDX IDs from a list of expressions, skipping UNKNOWN."""
    ids: set[str] = set()
    for expr in expressions:
        if expr != UNKNOWN_LICENSE:
            for lic in get_simple_licenses(expr):
                ids.add(lic)
    return list(ids)


def _is_unknown(pkg: PackageLicense) -> bool:
    """Check if a package has an unknown or unrecognized license."""
    return (
        pkg.license_expression == UNKNOWN_LICENSE
        or pkg.category == LicenseCategory.UNKNOWN
    )


def _unknown_message(pkg: PackageLicense) -> str:
    """Build a human-readable message for an unknown license."""
    if pkg.license_expression == UNKNOWN_LICENSE:
        detail = f"License for '{pkg.name}' could not be detected."
    else:
        detail = (
            f"License '{pkg.license_expression}' for '{pkg.name}' "
            f"is not a recognized SPDX expression."
        )
    return (
        f"{detail} Add an override in [tool.license-audit.overrides] or check manually."
    )


def _denied_license_items(
    packages: list[PackageLicense], denied_licenses: list[str]
) -> list[ActionItem]:
    """Build action items for packages using denied licenses."""
    items: list[ActionItem] = []
    denied_set = {d.lower() for d in denied_licenses}
    for pkg in packages:
        for lic in get_simple_licenses(pkg.license_expression):
            if lic.lower() in denied_set:
                items.append(
                    ActionItem(
                        severity="error",
                        package=pkg.name,
                        message=(
                            f"Package '{pkg.name}' uses denied license '{lic}'. "
                            f"Find an alternative or request an exemption."
                        ),
                    )
                )
    return items


def _build_action_items(
    packages: list[PackageLicense],
    incompatible: list[CompatibilityResult],
    config: LicenseAuditConfig,
) -> list[ActionItem]:
    """Generate action items from the analysis."""
    items: list[ActionItem] = []

    # Unknown licenses (literal "UNKNOWN" or unrecognized expressions)
    for pkg in packages:
        if _is_unknown(pkg):
            items.append(
                ActionItem(
                    severity="warning",
                    package=pkg.name,
                    message=_unknown_message(pkg),
                )
            )

    # Incompatible pairs
    for pair in incompatible:
        items.append(
            ActionItem(
                severity="error",
                package="",
                message=(
                    f"Licenses '{pair.inbound}' and '{pair.outbound}' are mutually incompatible. "
                    f"Dependencies using these licenses cannot coexist."
                ),
            )
        )

    if config.denied_licenses:
        items.extend(_denied_license_items(packages, config.denied_licenses))

    # Policy type violations
    max_rank = _POLICY_MAX_RANK.get(config.policy)
    for pkg in packages:
        if _exceeds_policy_rank(pkg, max_rank):
            items.append(
                ActionItem(
                    severity="error",
                    package=pkg.name,
                    message=(
                        f"Package '{pkg.name}' uses {pkg.category.value} license "
                        f"'{pkg.license_expression}', which violates the "
                        f"'{config.policy}' policy."
                    ),
                )
            )
        elif pkg.category in (
            LicenseCategory.STRONG_COPYLEFT,
            LicenseCategory.NETWORK_COPYLEFT,
        ):
            items.append(
                ActionItem(
                    severity="warning",
                    package=pkg.name,
                    message=(
                        f"Package '{pkg.name}' uses {pkg.category.value} license "
                        f"'{pkg.license_expression}'. This may require your project to use "
                        f"a compatible copyleft license."
                    ),
                )
            )

    return items


def _build_policy(config: LicenseAuditConfig) -> LicensePolicy:
    """Build a LicensePolicy from config."""
    return LicensePolicy(
        policy_type=config.policy,
        allowed_licenses=config.allowed_licenses,
        denied_licenses=config.denied_licenses,
        fail_on_unknown=config.fail_on_unknown,
    )


def _exceeds_policy_rank(pkg: PackageLicense, max_rank: int | None) -> bool:
    """Return True if a package's license category exceeds the policy threshold."""
    if max_rank is None or pkg.category == LicenseCategory.UNKNOWN:
        return False
    return CATEGORY_RANK.get(pkg.category, 5) > max_rank


def _check_policy(
    packages: list[PackageLicense],
    policy: LicensePolicy,
) -> bool:
    """Check if all packages satisfy the policy."""
    max_rank = _POLICY_MAX_RANK.get(policy.policy_type)

    denied_set = (
        {d.lower() for d in policy.denied_licenses} if policy.denied_licenses else set()
    )
    allowed_set = (
        {a.lower() for a in policy.allowed_licenses}
        if policy.allowed_licenses
        else set()
    )

    for pkg in packages:
        if policy.fail_on_unknown and (
            pkg.license_expression == UNKNOWN_LICENSE
            or pkg.category == LicenseCategory.UNKNOWN
        ):
            return False

        if _exceeds_policy_rank(pkg, max_rank):
            return False

        # Check denied list
        if denied_set:
            for lic in get_simple_licenses(pkg.license_expression):
                if lic.lower() in denied_set:
                    return False

        # Check allowed list (if specified, only these are allowed)
        if allowed_set:
            for lic in get_simple_licenses(pkg.license_expression):
                if (
                    lic.lower() not in allowed_set
                    and pkg.license_expression != UNKNOWN_LICENSE
                ):
                    return False

    return True
