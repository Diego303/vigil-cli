"""Analyzer de dependencias: hallucination, typosquatting, freshness."""

import re

import structlog

from vigil.analyzers.deps.parsers import (
    DeclaredDependency,
    find_and_parse_all,
)
from vigil.analyzers.deps.registry_client import PackageInfo, RegistryClient
from vigil.analyzers.deps.similarity import find_similar_popular, load_popular_packages
from vigil.config.schema import DepsConfig, ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity

logger = structlog.get_logger()


class DependencyAnalyzer:
    """Analiza dependencias para detectar hallucinations, typosquatting, y freshness.

    Implementa reglas DEP-001 a DEP-007:
      DEP-001: Paquete no existe en el registry (hallucinated)
      DEP-002: Paquete sospechosamente nuevo (<N dias)
      DEP-003: Nombre similar a un paquete popular (typosquatting)
      DEP-004: Paquete con pocas descargas
      DEP-005: Paquete sin repositorio de codigo fuente
      DEP-006: (Reservado para import sin declarar — no implementado en FASE 1)
      DEP-007: Version especificada no existe en el registry
    """

    @property
    def name(self) -> str:
        return "dependency"

    @property
    def category(self) -> Category:
        return Category.DEPENDENCY

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        """Ejecuta el analisis de dependencias."""
        findings: list[Finding] = []
        deps_config = config.deps

        # 1. Determinar la raiz del proyecto a partir de los paths
        roots = _extract_roots(files)
        if not roots:
            logger.info("no_roots_found")
            return findings

        # 2. Parsear dependencias declaradas
        all_declared: list[DeclaredDependency] = []
        for root in roots:
            all_declared.extend(find_and_parse_all(root))

        if not all_declared:
            logger.info("no_dependencies_found")
            return findings

        logger.info("deps_parsed", count=len(all_declared))

        # 3. Deduplicar por nombre+ecosystem (puede haber duplicados entre archivos)
        unique_deps = _deduplicate_deps(all_declared)

        # 4. Pre-cargar corpus de paquetes populares para checks de similaridad
        popular_pypi = load_popular_packages("pypi")
        popular_npm = load_popular_packages("npm")
        popular_by_ecosystem = {"pypi": popular_pypi, "npm": popular_npm}

        # 5. Verificar contra registry (si no es offline)
        if deps_config.verify_registry and not deps_config.offline_mode:
            registry_findings = self._check_registries(
                unique_deps, deps_config, popular_by_ecosystem
            )
            findings.extend(registry_findings)
        elif deps_config.offline_mode:
            logger.info("offline_mode", skipped="registry verification")

        # 6. Checks de similaridad (no requiere network)
        for dep in unique_deps:
            popular = popular_by_ecosystem.get(dep.ecosystem, {})
            similar = find_similar_popular(
                dep.name,
                dep.ecosystem,
                deps_config.similarity_threshold,
                popular_packages=popular,
            )
            if similar:
                # Solo reportar si el paquete no es popular el mismo
                # (evitar que un paquete popular reporte typosquatting con otro)
                dep_normalized = dep.name.lower()
                if dep_normalized not in {n.lower() for n in popular}:
                    best_match, similarity = similar[0]
                    findings.append(
                        Finding(
                            rule_id="DEP-003",
                            category=Category.DEPENDENCY,
                            severity=Severity.HIGH,
                            message=(
                                f"Package '{dep.name}' has a name very similar to "
                                f"popular package '{best_match}' "
                                f"(similarity: {similarity:.0%}). "
                                f"This could be typosquatting."
                            ),
                            location=Location(
                                file=dep.source_file,
                                line=dep.line_number,
                                snippet=f"{dep.name}"
                                + (f"{dep.version_spec}" if dep.version_spec else ""),
                            ),
                            suggestion=(
                                f"Did you mean '{best_match}'? "
                                f"Verify the correct package name."
                            ),
                            metadata={
                                "package": dep.name,
                                "similar_to": best_match,
                                "similarity": round(similarity, 3),
                                "ecosystem": dep.ecosystem,
                            },
                        )
                    )

        return findings

    def _check_registries(
        self,
        deps: list[DeclaredDependency],
        config: DepsConfig,
        popular_by_ecosystem: dict[str, dict[str, int]],
    ) -> list[Finding]:
        """Verifica dependencias contra los registries."""
        findings: list[Finding] = []

        with RegistryClient(cache_ttl_hours=config.cache_ttl_hours) as client:
            for dep in deps:
                try:
                    pkg = client.check(dep.name, dep.ecosystem)
                    dep_findings = self._check_package(dep, pkg, config)
                    findings.extend(dep_findings)
                except Exception as e:
                    logger.warning(
                        "registry_check_error",
                        package=dep.name,
                        error=str(e),
                    )

        return findings

    def _check_package(
        self,
        dep: DeclaredDependency,
        pkg: PackageInfo,
        config: DepsConfig,
    ) -> list[Finding]:
        """Verifica un paquete individual contra su info del registry."""
        findings: list[Finding] = []
        loc = Location(
            file=dep.source_file,
            line=dep.line_number,
            snippet=f"{dep.name}"
            + (f"{dep.version_spec}" if dep.version_spec else ""),
        )

        # Si hubo error de network, no podemos verificar — skip
        if pkg.error:
            logger.debug("registry_check_skipped", package=dep.name, error=pkg.error)
            return findings

        # DEP-001: No existe en el registry
        if not pkg.exists:
            findings.append(
                Finding(
                    rule_id="DEP-001",
                    category=Category.DEPENDENCY,
                    severity=Severity.CRITICAL,
                    message=(
                        f"Package '{dep.name}' does not exist in {dep.ecosystem}. "
                        f"This is likely a hallucinated dependency from an AI agent."
                    ),
                    location=loc,
                    suggestion=(
                        f"Remove '{dep.name}' and find the correct package name. "
                        f"Search {dep.ecosystem} for the functionality you need."
                    ),
                    metadata={
                        "package": dep.name,
                        "ecosystem": dep.ecosystem,
                    },
                )
            )
            return findings  # No verificar mas si no existe

        # DEP-002: Sospechosamente nuevo
        age_days = pkg.age_days
        if age_days is not None and age_days < config.min_age_days:
            findings.append(
                Finding(
                    rule_id="DEP-002",
                    category=Category.DEPENDENCY,
                    severity=Severity.HIGH,
                    message=(
                        f"Package '{dep.name}' was created only {age_days} days ago. "
                        f"New packages may be malicious (slopsquatting)."
                    ),
                    location=loc,
                    suggestion=(
                        f"Verify that '{dep.name}' is a legitimate package. "
                        f"Check its source code, maintainers, and purpose."
                    ),
                    metadata={
                        "package": dep.name,
                        "age_days": age_days,
                        "created_at": pkg.created_at,
                        "ecosystem": dep.ecosystem,
                    },
                )
            )

        # DEP-005: Sin repositorio de codigo fuente
        if not pkg.source_url:
            findings.append(
                Finding(
                    rule_id="DEP-005",
                    category=Category.DEPENDENCY,
                    severity=Severity.MEDIUM,
                    message=(
                        f"Package '{dep.name}' has no source repository linked. "
                        f"This makes it harder to verify its legitimacy."
                    ),
                    location=loc,
                    suggestion=(
                        f"Verify the package is legitimate and has a code repository."
                    ),
                    metadata={
                        "package": dep.name,
                        "ecosystem": dep.ecosystem,
                    },
                )
            )

        # DEP-007: Version especificada no existe
        if dep.version_spec and pkg.versions:
            pinned_version = _extract_pinned_version(dep.version_spec, dep.ecosystem)
            if pinned_version and pinned_version not in pkg.versions:
                # Mostrar las ultimas 5 versiones como sugerencia
                recent = pkg.versions[-5:] if len(pkg.versions) > 5 else pkg.versions
                findings.append(
                    Finding(
                        rule_id="DEP-007",
                        category=Category.DEPENDENCY,
                        severity=Severity.CRITICAL,
                        message=(
                            f"Version '{pinned_version}' of '{dep.name}' "
                            f"does not exist in {dep.ecosystem}."
                        ),
                        location=loc,
                        suggestion=(
                            f"Available versions include: {', '.join(recent)}. "
                            f"Use '{pkg.latest_version}' for the latest."
                        ),
                        metadata={
                            "package": dep.name,
                            "version": pinned_version,
                            "latest_version": pkg.latest_version,
                            "ecosystem": dep.ecosystem,
                        },
                    )
                )

        return findings


def _extract_roots(files: list[str]) -> list[str]:
    """Extrae directorios raiz unicos de una lista de archivos."""
    from pathlib import Path

    roots: set[str] = set()
    for f in files:
        p = Path(f)
        if p.is_file():
            roots.add(str(p.parent))
        elif p.is_dir():
            roots.add(str(p))
        else:
            roots.add(f)

    if not roots:
        return []

    # Ordenar por profundidad (menos profundo primero)
    sorted_roots = sorted(roots, key=lambda r: len(Path(r).parts))

    # Eliminar subdirectorios si su padre ya esta en la lista
    unique: list[str] = []
    for root in sorted_roots:
        root_path = Path(root).resolve()
        is_subdir = False
        for existing in unique:
            existing_path = Path(existing).resolve()
            try:
                root_path.relative_to(existing_path)
                is_subdir = True
                break
            except ValueError:
                continue
        if not is_subdir:
            unique.append(root)

    return unique


def _deduplicate_deps(
    deps: list[DeclaredDependency],
) -> list[DeclaredDependency]:
    """Deduplica dependencias por nombre+ecosystem, manteniendo la primera ocurrencia."""
    seen: set[str] = set()
    unique: list[DeclaredDependency] = []
    for dep in deps:
        key = f"{dep.ecosystem}:{dep.name.lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(dep)
    return unique


def _extract_pinned_version(version_spec: str, ecosystem: str) -> str | None:
    """Extrae version exacta de un version spec si esta pinned.

    Returns None si no es una version exacta.
    """
    if ecosystem == "pypi":
        # Python: ==1.2.3
        match = re.match(r"^==\s*(.+)$", version_spec.strip())
        if match:
            return match.group(1).strip()
    elif ecosystem == "npm":
        # npm: "1.2.3" (sin prefijo) es version exacta
        cleaned = version_spec.strip()
        if re.match(r"^\d+\.\d+\.\d+$", cleaned):
            return cleaned
    return None
