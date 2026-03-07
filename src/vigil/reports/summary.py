"""Resumen estadistico del scan."""

from typing import Any

from vigil.core.engine import ScanResult
from vigil.core.finding import Category, Severity


def build_summary(result: ScanResult) -> dict[str, Any]:
    """Construye un resumen estadistico del resultado del scan.

    Returns:
        Diccionario con estadisticas desglosadas por severidad, categoria,
        regla, y archivos mas afectados.
    """
    by_severity: dict[str, int] = {}
    for sev in Severity:
        count = sum(1 for f in result.findings if f.severity == sev)
        if count > 0:
            by_severity[sev.value] = count

    by_category: dict[str, int] = {}
    for cat in Category:
        count = sum(1 for f in result.findings if f.category == cat)
        if count > 0:
            by_category[cat.value] = count

    by_rule: dict[str, int] = {}
    for finding in result.findings:
        by_rule[finding.rule_id] = by_rule.get(finding.rule_id, 0) + 1

    # Top archivos con mas findings (max 10)
    by_file: dict[str, int] = {}
    for finding in result.findings:
        by_file[finding.location.file] = by_file.get(finding.location.file, 0) + 1
    top_files = dict(
        sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]
    )

    return {
        "files_scanned": result.files_scanned,
        "total_findings": len(result.findings),
        "duration_seconds": round(result.duration_seconds, 3),
        "analyzers_run": result.analyzers_run,
        "by_severity": by_severity,
        "by_category": by_category,
        "by_rule": by_rule,
        "by_file": top_files,
        "has_blocking": result.has_blocking_findings,
        "errors": result.errors,
    }
