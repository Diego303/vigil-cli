"""SARIF 2.1.0 output formatter."""

import json

from vigil import __version__
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


class SarifFormatter:
    """Formatea resultado del scan como SARIF 2.1.0."""

    def format(self, result: ScanResult) -> str:
        registry = RuleRegistry()

        # Recopilar reglas usadas en findings
        used_rule_ids = {f.rule_id for f in result.findings}

        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "vigil",
                            "version": __version__,
                            "informationUri": "https://github.com/org/vigil",
                            "rules": [
                                self._rule_to_sarif(registry.get(rid))
                                for rid in sorted(used_rule_ids)
                                if registry.get(rid)
                            ],
                        }
                    },
                    "results": [
                        self._finding_to_sarif(f) for f in result.findings
                    ],
                }
            ],
        }
        return json.dumps(sarif, indent=2)

    def _rule_to_sarif(self, rule) -> dict:
        entry: dict = {
            "id": rule.id,
            "name": "".join(w.capitalize() for w in rule.name.split()),
            "shortDescription": {"text": rule.description},
        }
        if rule.cwe_ref:
            entry["properties"] = {"cwe": rule.cwe_ref}
        return entry

    def _finding_to_sarif(self, finding: Finding) -> dict:
        location: dict = {
            "artifactLocation": {"uri": finding.location.file},
        }
        if finding.location.line is not None:
            region: dict = {"startLine": finding.location.line}
            if finding.location.column is not None:
                region["startColumn"] = finding.location.column
            if finding.location.end_line is not None:
                region["endLine"] = finding.location.end_line
            location["region"] = region

        entry: dict = {
            "ruleId": finding.rule_id,
            "level": _SEVERITY_TO_SARIF_LEVEL[finding.severity],
            "message": {"text": finding.message},
            "locations": [{"physicalLocation": location}],
        }
        if finding.suggestion:
            entry["fixes"] = [
                {"description": {"text": finding.suggestion}}
            ]
        return entry
