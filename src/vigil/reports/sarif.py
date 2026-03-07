"""SARIF 2.1.0 output formatter.

Genera output compatible con GitHub Code Scanning y GitLab SAST.
Referencia: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

import json
import re
from typing import Any

from vigil import __version__
from vigil.config.rules import RuleDefinition
from vigil.core.engine import ScanResult
from vigil.core.finding import Finding, Severity
from vigil.core.rule_registry import RuleRegistry

_SEVERITY_TO_SARIF_LEVEL: dict[Severity, str] = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}

# Regex para separar palabras en rule names (letras/numeros)
_WORD_SPLIT = re.compile(r"[\s\-_]+")


def _to_pascal_case(text: str) -> str:
    """Convierte texto a PascalCase para SARIF rule names."""
    return "".join(word.capitalize() for word in _WORD_SPLIT.split(text) if word)


class SarifFormatter:
    """Formatea resultado del scan como SARIF 2.1.0.

    SARIF es el estandar que GitHub y GitLab usan para mostrar findings de
    seguridad directamente en el PR. Al generar SARIF, vigil se integra
    automaticamente con GitHub Code Scanning y GitLab SAST.
    """

    def format(self, result: ScanResult) -> str:
        registry = RuleRegistry()

        # Recopilar reglas usadas en findings (orden alfabetico)
        used_rule_ids = sorted({f.rule_id for f in result.findings})

        # Construir indice rule_id → posicion para ruleIndex
        rule_index_map: dict[str, int] = {
            rid: idx for idx, rid in enumerate(used_rule_ids)
        }

        sarif: dict[str, Any] = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "vigil",
                            "version": __version__,
                            "semanticVersion": __version__,
                            "informationUri": "https://github.com/org/vigil",
                            "rules": [
                                self._rule_to_sarif(rule_def)
                                for rid in used_rule_ids
                                if (rule_def := registry.get(rid))
                            ],
                        }
                    },
                    "results": [
                        self._finding_to_sarif(f, rule_index_map)
                        for f in result.findings
                    ],
                    "invocations": [
                        {
                            "executionSuccessful": len(result.errors) == 0,
                            "toolExecutionNotifications": [
                                {
                                    "level": "error",
                                    "message": {"text": err},
                                }
                                for err in result.errors
                            ],
                        }
                    ],
                }
            ],
        }
        return json.dumps(sarif, indent=2)

    def _rule_to_sarif(self, rule: RuleDefinition) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": rule.id,
            "name": _to_pascal_case(rule.name),
            "shortDescription": {"text": rule.description},
            "defaultConfiguration": {
                "level": _SEVERITY_TO_SARIF_LEVEL[rule.default_severity],
            },
            "helpUri": f"https://github.com/org/vigil/docs/rules/{rule.id}",
        }
        properties: dict[str, Any] = {}
        if rule.cwe_ref:
            properties["cwe"] = rule.cwe_ref
        if rule.owasp_ref:
            properties["owasp"] = rule.owasp_ref
        if properties:
            entry["properties"] = properties
        return entry

    def _finding_to_sarif(
        self,
        finding: Finding,
        rule_index_map: dict[str, int],
    ) -> dict[str, Any]:
        physical_location: dict[str, Any] = {
            "artifactLocation": {"uri": finding.location.file},
        }
        if finding.location.line is not None:
            region: dict[str, Any] = {"startLine": finding.location.line}
            if finding.location.column is not None:
                region["startColumn"] = finding.location.column
            if finding.location.end_line is not None:
                region["endLine"] = finding.location.end_line
            if finding.location.snippet is not None:
                region["snippet"] = {"text": finding.location.snippet}
            physical_location["region"] = region

        entry: dict[str, Any] = {
            "ruleId": finding.rule_id,
            "ruleIndex": rule_index_map[finding.rule_id],
            "level": _SEVERITY_TO_SARIF_LEVEL[finding.severity],
            "message": {"text": finding.message},
            "locations": [{"physicalLocation": physical_location}],
        }
        if finding.suggestion:
            entry["fixes"] = [
                {"description": {"text": finding.suggestion}}
            ]
        return entry
