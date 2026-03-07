"""Edge case tests para formatters."""

import json
import xml.etree.ElementTree as ET

import pytest

from vigil.core.engine import ScanResult
from vigil.core.finding import Category, Finding, Location, Severity
from vigil.reports.formatter import get_formatter
from vigil.reports.human import HumanFormatter
from vigil.reports.json_fmt import JsonFormatter
from vigil.reports.junit import JunitFormatter
from vigil.reports.sarif import SarifFormatter
from vigil.reports.summary import build_summary


def _make_finding(
    rule_id: str = "DEP-001",
    severity: Severity = Severity.CRITICAL,
    category: Category = Category.DEPENDENCY,
    file: str = "test.py",
    line: int | None = 1,
    suggestion: str | None = None,
    snippet: str | None = None,
    column: int | None = None,
    end_line: int | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        category=category,
        severity=severity,
        message=f"Finding for {rule_id}",
        location=Location(
            file=file, line=line, column=column,
            end_line=end_line, snippet=snippet,
        ),
        suggestion=suggestion,
    )


# ── JSON Formatter ──────────────────────────────────────────


class TestJsonFormatterEdgeCases:
    def test_finding_with_all_fields(self):
        finding = _make_finding(
            suggestion="Fix this",
            column=5,
            end_line=10,
            snippet="import os",
        )
        finding.metadata = {"key": "value", "nested": {"a": 1}}
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        f = data["findings"][0]
        assert f["location"]["column"] == 5
        assert f["location"]["end_line"] == 10
        assert f["suggestion"] == "Fix this"
        assert f["metadata"]["key"] == "value"

    def test_finding_with_no_line(self):
        """Finding sin numero de linea (ej: pyproject.toml parsed)."""
        finding = _make_finding(line=None)
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["findings"][0]["location"]["line"] is None

    def test_special_characters_in_message(self):
        """Caracteres especiales en mensaje se escapan en JSON."""
        finding = _make_finding()
        finding.message = 'Path: "C:\\Users\\test" has <special> & chars'
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert '"C:\\Users\\test"' in data["findings"][0]["message"]

    def test_unicode_in_findings(self):
        finding = _make_finding(file="archivo_espanol.py")
        finding.message = "Paquete 'test' no existe en el registro publico"
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["findings"][0]["location"]["file"] == "archivo_espanol.py"

    def test_many_findings(self):
        """Muchos findings no causan problemas."""
        findings = [_make_finding(rule_id=f"X-{i:03d}") for i in range(100)]
        result = ScanResult(findings=findings)
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["findings_count"] == 100

    def test_errors_included(self):
        result = ScanResult(errors=["Error 1", "Error 2"])
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["errors"] == ["Error 1", "Error 2"]

    def test_version_field(self):
        result = ScanResult()
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["version"] == "0.5.0"


# ── JUnit Formatter ─────────────────────────────────────────


class TestJunitFormatterEdgeCases:
    def test_xml_declaration_present(self):
        result = ScanResult()
        formatter = JunitFormatter()
        output = formatter.format(result)
        assert output.startswith("<?xml")

    def test_failure_type_error_for_critical(self):
        finding = _make_finding(severity=Severity.CRITICAL)
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert failure.get("type") == "error"

    def test_failure_type_warning_for_medium(self):
        finding = _make_finding(severity=Severity.MEDIUM)
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert failure.get("type") == "warning"

    def test_failure_type_warning_for_low(self):
        finding = _make_finding(severity=Severity.LOW)
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert failure.get("type") == "warning"

    def test_failure_text_contains_rule_info(self):
        finding = _make_finding(
            rule_id="SEC-001",
            severity=Severity.CRITICAL,
            suggestion="Use env vars",
        )
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert "Rule: SEC-001" in failure.text
        assert "Severity: critical" in failure.text
        assert "Suggestion: Use env vars" in failure.text

    def test_with_errors(self):
        result = ScanResult(errors=["Analyzer X failed"])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("errors") == "1"
        error_case = root.find(".//error")
        assert error_case is not None

    def test_special_xml_chars_escaped(self):
        """Caracteres especiales XML se escapan correctamente."""
        finding = _make_finding()
        finding.message = 'Value <script> & "quotes" in message'
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        # Should not crash when parsing
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert "&" in failure.get("message") or "&amp;" in output


# ── SARIF Formatter ─────────────────────────────────────────


class TestSarifFormatterEdgeCases:
    def test_sarif_structure_complete(self):
        finding = _make_finding(
            suggestion="Fix it",
            column=5,
            end_line=10,
        )
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        assert data["version"] == "2.1.0"
        run = data["runs"][0]
        assert run["tool"]["driver"]["name"] == "vigil"
        assert len(run["results"]) == 1

        sarif_result = run["results"][0]
        assert sarif_result["ruleId"] == "DEP-001"
        assert sarif_result["level"] == "error"
        loc = sarif_result["locations"][0]["physicalLocation"]
        assert loc["region"]["startLine"] == 1
        assert loc["region"]["startColumn"] == 5
        assert loc["region"]["endLine"] == 10

    def test_sarif_fix_in_result(self):
        finding = _make_finding(suggestion="Use os.environ")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        sarif_result = data["runs"][0]["results"][0]
        assert "fixes" in sarif_result
        assert sarif_result["fixes"][0]["description"]["text"] == "Use os.environ"

    def test_sarif_no_fix_when_no_suggestion(self):
        finding = _make_finding(suggestion=None)
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        sarif_result = data["runs"][0]["results"][0]
        assert "fixes" not in sarif_result

    def test_sarif_rules_only_for_used_rules(self):
        """Solo las reglas usadas aparecen en el SARIF driver.rules."""
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
        ]
        result = ScanResult(findings=findings)
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert rule_ids == {"AUTH-005", "DEP-001"}

    @pytest.mark.parametrize("severity,expected_level", [
        (Severity.CRITICAL, "error"),
        (Severity.HIGH, "error"),
        (Severity.MEDIUM, "warning"),
        (Severity.LOW, "note"),
        (Severity.INFO, "note"),
    ])
    def test_sarif_severity_mapping(self, severity, expected_level):
        finding = _make_finding(severity=severity)
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["runs"][0]["results"][0]["level"] == expected_level

    def test_sarif_finding_without_line(self):
        """Finding sin linea no incluye region."""
        finding = _make_finding(line=None)
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        loc = data["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert "region" not in loc

    def test_sarif_rule_name_pascal_case(self):
        """Rule names are proper PascalCase (fixed in FASE 4)."""
        finding = _make_finding("DEP-001")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        dep_rule = [r for r in rules if r["id"] == "DEP-001"][0]
        assert dep_rule["name"] == "HallucinatedDependency"


# ── Human Formatter ─────────────────────────────────────────


class TestHumanFormatterEdgeCases:
    def test_snippet_shown(self):
        finding = _make_finding(snippet='SECRET_KEY = "changeme"')
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "changeme" in output

    def test_all_severity_icons(self):
        """Todos los niveles de severity se formatean sin error."""
        for sev in Severity:
            finding = _make_finding(severity=sev)
            result = ScanResult(findings=[finding], files_scanned=1)
            formatter = HumanFormatter()
            output = formatter.format(result)
            assert finding.rule_id in output

    def test_version_in_header(self):
        result = ScanResult(files_scanned=5)
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "v0.5.0" in output

    def test_analyzer_names_listed(self):
        result = ScanResult(
            files_scanned=5,
            analyzers_run=["dependency", "auth", "secrets"],
        )
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "dependency" in output
        assert "auth" in output
        assert "secrets" in output


# ── Summary ─────────────────────────────────────────────────


class TestSummaryEdgeCases:
    def test_summary_by_rule(self):
        findings = [
            _make_finding("DEP-001"),
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
        ]
        result = ScanResult(findings=findings, files_scanned=10)
        summary = build_summary(result)
        assert summary["by_rule"]["DEP-001"] == 2
        assert summary["by_rule"]["AUTH-005"] == 1

    def test_summary_duration_rounded(self):
        result = ScanResult(duration_seconds=1.23456789)
        summary = build_summary(result)
        assert summary["duration_seconds"] == 1.235

    def test_summary_empty_categories_not_in_output(self):
        """Categorias sin findings no aparecen en by_category."""
        result = ScanResult(findings=[], files_scanned=10)
        summary = build_summary(result)
        assert summary["by_category"] == {}
        assert summary["by_severity"] == {}
