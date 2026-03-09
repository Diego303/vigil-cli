"""ScanEngine — orquestador principal de vigil."""

from dataclasses import dataclass, field
import time

import structlog

from vigil.config.schema import ScanConfig
from vigil.core.file_collector import collect_files
from vigil.core.finding import Finding, Severity

logger = structlog.get_logger()


@dataclass
class ScanResult:
    """Resultado completo de un scan."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    duration_seconds: float = 0.0
    analyzers_run: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.LOW)

    @property
    def has_blocking_findings(self) -> bool:
        return any(f.is_blocking for f in self.findings)

    def findings_above(self, threshold: Severity) -> list[Finding]:
        """Retorna findings con severidad >= threshold."""
        severity_order = [
            Severity.INFO,
            Severity.LOW,
            Severity.MEDIUM,
            Severity.HIGH,
            Severity.CRITICAL,
        ]
        threshold_idx = severity_order.index(threshold)
        return [
            f
            for f in self.findings
            if severity_order.index(f.severity) >= threshold_idx
        ]


SEVERITY_SORT_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class ScanEngine:
    """Orquestador principal de vigil."""

    def __init__(self, config: ScanConfig) -> None:
        self.config = config
        self.analyzers: list = []

    def register_analyzer(self, analyzer: object) -> None:
        self.analyzers.append(analyzer)

    def run(self, paths: list[str]) -> ScanResult:
        start = time.time()
        result = ScanResult()

        # 1. Recopilar archivos
        files = self._collect_files(paths)
        result.files_scanned = len(files)
        logger.info("files_collected", count=len(files))

        # 2. Ejecutar cada analyzer
        for analyzer in self.analyzers:
            if not self._should_run(analyzer):
                logger.debug("analyzer_skipped", name=analyzer.name)
                continue
            try:
                logger.info("analyzer_start", name=analyzer.name)
                findings = analyzer.analyze(files, self.config)
                result.findings.extend(findings)
                result.analyzers_run.append(analyzer.name)
                logger.info(
                    "analyzer_done",
                    name=analyzer.name,
                    findings=len(findings),
                )
            except Exception as e:
                error_msg = f"Analyzer {analyzer.name} failed: {e}"
                result.errors.append(error_msg)
                logger.error("analyzer_error", name=analyzer.name, error=str(e))

        result.duration_seconds = time.time() - start

        # 3. Aplicar severity overrides y filtrar deshabilitadas
        self._apply_rule_overrides(result)

        # 4. Ordenar por severidad (critical primero)
        result.findings.sort(key=lambda f: SEVERITY_SORT_ORDER[f.severity])

        return result

    def _collect_files(self, paths: list[str]) -> list[str]:
        """Recopila archivos a escanear segun config."""
        return collect_files(
            paths=paths,
            exclude=self.config.exclude,
            languages=self.config.languages,
        )

    def _should_run(self, analyzer: object) -> bool:
        """Determina si un analyzer debe ejecutarse segun filtros de config."""
        if self.config.categories:
            if hasattr(analyzer, "category") and analyzer.category.value not in self.config.categories:
                return False
        if self.config.rules_filter:
            # Si hay filtro de reglas, solo ejecutar analyzers que tengan alguna regla en el filtro
            # Esto se implementara completamente cuando tengamos el rule_registry
            pass
        return True

    def _apply_rule_overrides(self, result: ScanResult) -> None:
        """Aplica overrides de reglas desde config."""
        filtered: list[Finding] = []
        # CLI --rule flag has priority over config enabled: false
        explicitly_requested = set(self.config.rules_filter) if self.config.rules_filter else set()
        for finding in result.findings:
            override = self.config.rules.get(finding.rule_id)
            if override:
                if override.enabled is False and finding.rule_id not in explicitly_requested:
                    continue
                if override.severity:
                    finding.severity = Severity(override.severity)
            # Filtrar reglas excluidas
            if finding.rule_id in self.config.exclude_rules:
                continue
            # Filtrar por rules_filter (--rule flag): solo incluir si esta en la lista
            if self.config.rules_filter and finding.rule_id not in self.config.rules_filter:
                continue
            filtered.append(finding)
        result.findings = filtered
