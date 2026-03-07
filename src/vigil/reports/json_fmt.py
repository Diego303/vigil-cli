"""JSON output formatter."""

import json
from typing import Any

from vigil import __version__
from vigil.core.engine import ScanResult
from vigil.core.finding import Finding
from vigil.reports.summary import build_summary


class JsonFormatter:
    """Formatea resultado del scan como JSON."""

    def format(self, result: ScanResult) -> str:
        output: dict[str, Any] = {
            "version": __version__,
            "files_scanned": result.files_scanned,
            "duration_seconds": round(result.duration_seconds, 3),
            "analyzers_run": result.analyzers_run,
            "findings_count": len(result.findings),
            "findings": [self._finding_to_dict(f) for f in result.findings],
            "summary": build_summary(result),
            "errors": result.errors,
        }
        return json.dumps(output, indent=2, default=str)

    def _finding_to_dict(self, finding: Finding) -> dict[str, Any]:
        location: dict[str, Any] = {
            "file": finding.location.file,
            "line": finding.location.line,
            "column": finding.location.column,
            "end_line": finding.location.end_line,
        }
        if finding.location.snippet is not None:
            location["snippet"] = finding.location.snippet

        return {
            "rule_id": finding.rule_id,
            "category": finding.category.value,
            "severity": finding.severity.value,
            "message": finding.message,
            "location": location,
            "suggestion": finding.suggestion,
            "metadata": finding.metadata,
        }
