"""Tests FASE 4 — Reports + Formatters polish.

Cubre las mejoras implementadas en FASE 4:
- HumanFormatter: quiet mode, show_suggestions, colors config, unicode icons,
  analyzer checkmarks, green "No findings" message
- JsonFormatter: summary inclusion, snippet in location
- JunitFormatter: properties element, category in failure text, snippet in failure
- SarifFormatter: PascalCase fix, helpUri, snippet in region, ruleIndex,
  invocations, defaultConfiguration, semanticVersion, owasp in properties
- Summary: by_file stats
"""

import json
import xml.etree.ElementTree as ET

from vigil.core.engine import ScanResult
from vigil.core.finding import Category, Finding, Location, Severity
from vigil.reports.formatter import get_formatter
from vigil.reports.human import HumanFormatter
from vigil.reports.json_fmt import JsonFormatter
from vigil.reports.junit import JunitFormatter
from vigil.reports.sarif import SarifFormatter, _to_pascal_case
from vigil.reports.summary import build_summary


def _make_finding(
    rule_id: str = "DEP-001",
    severity: Severity = Severity.CRITICAL,
    category: Category = Category.DEPENDENCY,
    file: str = "test.py",
    line: int | None = 1,
    suggestion: str | None = "Fix this issue",
    snippet: str | None = None,
    column: int | None = None,
    end_line: int | None = None,
    message: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        category=category,
        severity=severity,
        message=message or f"Finding for {rule_id}",
        location=Location(
            file=file, line=line, column=column,
            end_line=end_line, snippet=snippet,
        ),
        suggestion=suggestion,
    )


def _make_sample_result() -> ScanResult:
    """ScanResult con findings variados para tests integrales."""
    return ScanResult(
        findings=[
            _make_finding("DEP-001", Severity.CRITICAL, Category.DEPENDENCY,
                          "requirements.txt", 5, "Remove this dependency.",
                          message="Package 'nonexistent' does not exist."),
            _make_finding("AUTH-005", Severity.HIGH, Category.AUTH,
                          "src/main.py", 8, "Restrict CORS origins.",
                          snippet='allow_origins=["*"]',
                          message="CORS allows all origins."),
            _make_finding("SEC-002", Severity.CRITICAL, Category.SECRETS,
                          "src/config.py", 15, "Use env vars.",
                          snippet='SECRET = "changeme"',
                          message="Low-entropy hardcoded secret."),
            _make_finding("AUTH-003", Severity.MEDIUM, Category.AUTH,
                          "src/auth.py", 31, None,
                          message="JWT lifetime of 72 hours."),
            _make_finding("TEST-001", Severity.HIGH, Category.TEST_QUALITY,
                          "tests/test_app.py", 10, "Add assertions.",
                          message="Test has no assertions."),
        ],
        files_scanned=42,
        duration_seconds=1.234,
        analyzers_run=["dependency", "auth", "secrets", "test-quality"],
    )


# ═══════════════════════════════════════════════════════════
# HumanFormatter — FASE 4 improvements
# ═══════════════════════════════════════════════════════════


class TestHumanFormatterQuietMode:
    """Tests para --quiet mode (solo findings, sin header/summary)."""

    def test_quiet_no_header(self):
        result = _make_sample_result()
        formatter = HumanFormatter(quiet=True)
        output = formatter.format(result)
        assert "vigil" not in output.split("\n")[0] or "scanning" not in output

    def test_quiet_no_summary(self):
        result = _make_sample_result()
        formatter = HumanFormatter(quiet=True)
        output = formatter.format(result)
        assert "files scanned" not in output
        assert "analyzers:" not in output.lower()

    def test_quiet_findings_still_shown(self):
        result = _make_sample_result()
        formatter = HumanFormatter(quiet=True)
        output = formatter.format(result)
        assert "DEP-001" in output
        assert "AUTH-005" in output

    def test_quiet_empty_result_no_output(self):
        result = ScanResult(files_scanned=10)
        formatter = HumanFormatter(quiet=True)
        output = formatter.format(result)
        # No findings and quiet = minimal output
        assert "No findings" not in output

    def test_quiet_errors_still_shown(self):
        result = ScanResult(errors=["Analyzer failed"])
        formatter = HumanFormatter(quiet=True)
        output = formatter.format(result)
        assert "Analyzer failed" in output


class TestHumanFormatterShowSuggestions:
    """Tests para show_suggestions config."""

    def test_suggestions_shown_by_default(self):
        finding = _make_finding(suggestion="Remove this dependency")
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "Suggestion" in output
        assert "Remove this dependency" in output

    def test_suggestions_hidden_when_disabled(self):
        finding = _make_finding(suggestion="Remove this dependency")
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(show_suggestions=False)
        output = formatter.format(result)
        assert "Suggestion" not in output
        assert "Remove this dependency" not in output

    def test_finding_without_suggestion_no_arrow(self):
        finding = _make_finding(suggestion=None)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "Suggestion" not in output


class TestHumanFormatterColors:
    """Tests para config de colores."""

    def test_colors_disabled(self):
        finding = _make_finding()
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        # No ANSI escape codes
        assert "\033[" not in output

    def test_colors_disabled_still_has_content(self):
        result = _make_sample_result()
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "DEP-001" in output
        assert "vigil" in output


class TestHumanFormatterUnicodeIcons:
    """Tests para iconos Unicode."""

    def test_critical_uses_cross_mark(self):
        finding = _make_finding(severity=Severity.CRITICAL)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "\u2717" in output  # ✗

    def test_high_uses_cross_mark(self):
        finding = _make_finding(severity=Severity.HIGH)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "\u2717" in output  # ✗

    def test_medium_uses_warning(self):
        finding = _make_finding(severity=Severity.MEDIUM)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "\u26a0" in output  # ⚠


class TestHumanFormatterAnalyzerCheckmarks:
    """Tests para checkmarks en analyzers."""

    def test_analyzers_with_checkmarks(self):
        result = ScanResult(
            files_scanned=5,
            analyzers_run=["dependency", "auth"],
        )
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "dependency \u2713" in output  # ✓
        assert "auth \u2713" in output

    def test_analyzer_count_shown(self):
        result = ScanResult(
            files_scanned=5,
            analyzers_run=["dependency", "auth", "secrets"],
        )
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "3 analyzers:" in output


class TestHumanFormatterSuggestionArrow:
    """Tests para flecha de sugerencia Unicode."""

    def test_suggestion_uses_arrow(self):
        finding = _make_finding(suggestion="Fix this")
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "\u2192" in output  # →


class TestHumanFormatterHeader:
    """Tests para el header con em-dash y scanning text."""

    def test_header_shows_scanning(self):
        result = ScanResult(files_scanned=42)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "scanning 42 files" in output

    def test_no_findings_green_message(self):
        result = ScanResult(files_scanned=10)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "No findings." in output


class TestHumanFormatterSummaryLine:
    """Tests para la linea de resumen con Unicode box-drawing."""

    def test_summary_uses_box_drawing_dash(self):
        result = ScanResult(files_scanned=10)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "\u2500" in output  # ─ (box drawing horizontal)

    def test_info_severity_in_counts(self):
        """INFO severity se incluye en counts si existe."""
        findings = [_make_finding(severity=Severity.INFO)]
        result = ScanResult(findings=findings, files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "1 info" in output


class TestHumanFormatterIntegral:
    """Test integral del formatter completo."""

    def test_full_output_structure(self):
        result = _make_sample_result()
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)

        # Header
        assert "vigil" in output
        assert "scanning 42 files" in output

        # All findings present
        assert "DEP-001" in output
        assert "AUTH-005" in output
        assert "SEC-002" in output
        assert "AUTH-003" in output
        assert "TEST-001" in output

        # Summary
        assert "42 files scanned" in output
        assert "5 findings" in output
        assert "2 critical" in output
        assert "2 high" in output
        assert "1 medium" in output
        assert "4 analyzers:" in output


# ═══════════════════════════════════════════════════════════
# JsonFormatter — FASE 4 improvements
# ═══════════════════════════════════════════════════════════


class TestJsonFormatterSummary:
    """Tests para summary section en JSON output."""

    def test_summary_included(self):
        result = _make_sample_result()
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert "summary" in data
        summary = data["summary"]
        assert summary["total_findings"] == 5
        assert summary["files_scanned"] == 42
        assert summary["has_blocking"] is True

    def test_summary_by_severity(self):
        result = _make_sample_result()
        formatter = JsonFormatter()
        data = json.loads(formatter.format(result))
        assert data["summary"]["by_severity"]["critical"] == 2
        assert data["summary"]["by_severity"]["high"] == 2
        assert data["summary"]["by_severity"]["medium"] == 1

    def test_summary_by_category(self):
        result = _make_sample_result()
        formatter = JsonFormatter()
        data = json.loads(formatter.format(result))
        by_cat = data["summary"]["by_category"]
        assert by_cat["dependency"] == 1
        assert by_cat["auth"] == 2
        assert by_cat["secrets"] == 1
        assert by_cat["test-quality"] == 1

    def test_summary_empty_result(self):
        result = ScanResult(files_scanned=5)
        formatter = JsonFormatter()
        data = json.loads(formatter.format(result))
        assert data["summary"]["total_findings"] == 0
        assert data["summary"]["by_severity"] == {}


class TestJsonFormatterSnippet:
    """Tests para snippet en location."""

    def test_snippet_included_when_present(self):
        finding = _make_finding(snippet='SECRET = "changeme"')
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        data = json.loads(formatter.format(result))
        loc = data["findings"][0]["location"]
        assert loc["snippet"] == 'SECRET = "changeme"'

    def test_snippet_absent_when_none(self):
        finding = _make_finding(snippet=None)
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        data = json.loads(formatter.format(result))
        loc = data["findings"][0]["location"]
        assert "snippet" not in loc

    def test_json_with_all_location_fields(self):
        finding = _make_finding(
            column=5, end_line=10, snippet="import os",
        )
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        data = json.loads(formatter.format(result))
        loc = data["findings"][0]["location"]
        assert loc["line"] == 1
        assert loc["column"] == 5
        assert loc["end_line"] == 10
        assert loc["snippet"] == "import os"


# ═══════════════════════════════════════════════════════════
# JunitFormatter — FASE 4 improvements
# ═══════════════════════════════════════════════════════════


class TestJunitFormatterProperties:
    """Tests para el elemento <properties> en JUnit XML."""

    def test_properties_element_present(self):
        result = ScanResult(files_scanned=10)
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        props = root.find(".//properties")
        assert props is not None

    def test_version_property(self):
        result = ScanResult(files_scanned=5)
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        props = root.findall(".//property")
        version_prop = [p for p in props if p.get("name") == "vigil.version"]
        assert len(version_prop) == 1

    def test_files_scanned_property(self):
        result = ScanResult(files_scanned=42)
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        props = root.findall(".//property")
        files_prop = [p for p in props if p.get("name") == "vigil.files_scanned"]
        assert len(files_prop) == 1
        assert files_prop[0].get("value") == "42"

    def test_analyzers_property(self):
        result = ScanResult(analyzers_run=["dependency", "auth"])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        props = root.findall(".//property")
        analyzers_prop = [p for p in props if p.get("name") == "vigil.analyzers"]
        assert len(analyzers_prop) == 1
        assert analyzers_prop[0].get("value") == "dependency,auth"

    def test_no_analyzers_property_when_empty(self):
        result = ScanResult(analyzers_run=[])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        props = root.findall(".//property")
        analyzers_prop = [p for p in props if p.get("name") == "vigil.analyzers"]
        assert len(analyzers_prop) == 0


class TestJunitFormatterCategory:
    """Tests para category en failure text."""

    def test_category_in_failure_text(self):
        finding = _make_finding(category=Category.AUTH, rule_id="AUTH-005")
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert "Category: auth" in failure.text


class TestJunitFormatterSnippet:
    """Tests para snippet en failure text."""

    def test_snippet_in_failure_text(self):
        finding = _make_finding(snippet='app.cors(origin="*")')
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert 'Snippet: app.cors(origin="*")' in failure.text

    def test_no_snippet_when_none(self):
        finding = _make_finding(snippet=None)
        result = ScanResult(findings=[finding])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert "Snippet" not in failure.text


class TestJunitFormatterIntegral:
    """Test integral del JUnit formatter."""

    def test_full_junit_valid_xml(self):
        result = _make_sample_result()
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        assert root.tag == "testsuites"
        suite = root.find("testsuite")
        assert suite.get("name") == "vigil"
        assert suite.get("failures") == "5"
        assert suite.get("tests") == "5"
        testcases = suite.findall("testcase")
        assert len(testcases) == 5

    def test_junit_classnames_by_category(self):
        result = _make_sample_result()
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        classnames = {tc.get("classname") for tc in root.findall(".//testcase")}
        assert "vigil.dependency" in classnames
        assert "vigil.auth" in classnames

    def test_junit_output_to_file(self, tmp_path):
        """Verifica que el output XML se puede escribir a archivo."""
        result = _make_sample_result()
        formatter = JunitFormatter()
        output = formatter.format(result)
        xml_file = tmp_path / "report.xml"
        xml_file.write_text(output, encoding="utf-8")
        # Re-parse from file
        tree = ET.parse(str(xml_file))
        assert tree.getroot().tag == "testsuites"


# ═══════════════════════════════════════════════════════════
# SarifFormatter — FASE 4 improvements
# ═══════════════════════════════════════════════════════════


class TestSarifPascalCase:
    """Tests para la correccion del bug de PascalCase en rule names."""

    def test_pascal_case_basic(self):
        assert _to_pascal_case("Hallucinated dependency") == "HallucinatedDependency"

    def test_pascal_case_with_hyphens(self):
        assert _to_pascal_case("no-source-repository") == "NoSourceRepository"

    def test_pascal_case_with_underscores(self):
        assert _to_pascal_case("test_without_assertions") == "TestWithoutAssertions"

    def test_pascal_case_single_word(self):
        assert _to_pascal_case("test") == "Test"

    def test_pascal_case_empty(self):
        assert _to_pascal_case("") == ""

    def test_sarif_rule_name_is_pascal_case(self):
        """Rule name in SARIF output is proper PascalCase."""
        finding = _make_finding("DEP-001")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        dep_rule = [r for r in rules if r["id"] == "DEP-001"][0]
        assert dep_rule["name"] == "HallucinatedDependency"


class TestSarifHelpUri:
    """Tests para helpUri en rules."""

    def test_help_uri_present(self):
        finding = _make_finding("DEP-001")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        dep_rule = [r for r in rules if r["id"] == "DEP-001"][0]
        assert "helpUri" in dep_rule
        assert "DEP-001" in dep_rule["helpUri"]

    def test_help_uri_for_each_rule(self):
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
        ]
        result = ScanResult(findings=findings)
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        for rule in rules:
            assert "helpUri" in rule
            assert rule["id"] in rule["helpUri"]


class TestSarifSnippet:
    """Tests para snippet in region."""

    def test_snippet_in_region(self):
        finding = _make_finding(snippet='SECRET = "changeme"', line=5)
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        region = data["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert "snippet" in region
        assert region["snippet"]["text"] == 'SECRET = "changeme"'

    def test_no_snippet_when_none(self):
        finding = _make_finding(snippet=None, line=5)
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        region = data["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert "snippet" not in region


class TestSarifRuleIndex:
    """Tests para ruleIndex en results."""

    def test_rule_index_present(self):
        finding = _make_finding("DEP-001")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        sarif_result = data["runs"][0]["results"][0]
        assert "ruleIndex" in sarif_result
        assert sarif_result["ruleIndex"] == 0

    def test_rule_index_corresponds_to_rules_array(self):
        """ruleIndex matches the position in the driver.rules array."""
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
            _make_finding("DEP-001"),  # duplicate rule
        ]
        result = ScanResult(findings=findings)
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        results = data["runs"][0]["results"]

        # Rules are sorted: AUTH-005 (idx 0), DEP-001 (idx 1)
        rule_ids = [r["id"] for r in rules]
        assert rule_ids == ["AUTH-005", "DEP-001"]

        # Results reference correct indices
        assert results[0]["ruleIndex"] == 1  # DEP-001 → idx 1
        assert results[1]["ruleIndex"] == 0  # AUTH-005 → idx 0
        assert results[2]["ruleIndex"] == 1  # DEP-001 → idx 1


class TestSarifInvocations:
    """Tests para invocations en SARIF output."""

    def test_invocation_present(self):
        result = ScanResult(files_scanned=5)
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        invocations = data["runs"][0]["invocations"]
        assert len(invocations) == 1
        assert invocations[0]["executionSuccessful"] is True

    def test_invocation_with_errors(self):
        result = ScanResult(errors=["Analyzer dep failed: timeout"])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        inv = data["runs"][0]["invocations"][0]
        assert inv["executionSuccessful"] is False
        assert len(inv["toolExecutionNotifications"]) == 1
        assert "timeout" in inv["toolExecutionNotifications"][0]["message"]["text"]

    def test_invocation_multiple_errors(self):
        result = ScanResult(errors=["Error 1", "Error 2"])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        inv = data["runs"][0]["invocations"][0]
        assert inv["executionSuccessful"] is False
        assert len(inv["toolExecutionNotifications"]) == 2


class TestSarifDefaultConfiguration:
    """Tests para defaultConfiguration en rules."""

    def test_default_configuration_present(self):
        finding = _make_finding("DEP-001")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]
        assert "defaultConfiguration" in rule
        assert rule["defaultConfiguration"]["level"] == "error"

    def test_default_configuration_medium_warning(self):
        finding = _make_finding("AUTH-003", severity=Severity.MEDIUM, category=Category.AUTH)
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["defaultConfiguration"]["level"] == "warning"


class TestSarifSemanticVersion:
    """Tests para semanticVersion en tool driver."""

    def test_semantic_version_present(self):
        result = ScanResult()
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        driver = data["runs"][0]["tool"]["driver"]
        assert "semanticVersion" in driver
        assert driver["semanticVersion"] == driver["version"]


class TestSarifOwaspProperty:
    """Tests para OWASP ref en rule properties."""

    def test_owasp_in_properties(self):
        finding = _make_finding("DEP-001")  # Has owasp_ref="LLM03"
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]
        assert "properties" in rule
        assert rule["properties"]["owasp"] == "LLM03"

    def test_cwe_and_owasp_both_present(self):
        finding = _make_finding("DEP-001")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]
        props = rule["properties"]
        assert "cwe" in props
        assert "owasp" in props


class TestSarifIntegral:
    """Test integral del SARIF formatter."""

    def test_full_sarif_valid_json(self):
        result = _make_sample_result()
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)

        # Top-level structure
        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1

        run = data["runs"][0]

        # Tool info
        driver = run["tool"]["driver"]
        assert driver["name"] == "vigil"
        assert "semanticVersion" in driver

        # Rules (should be unique set of used rule IDs)
        rule_ids = {r["id"] for r in driver["rules"]}
        assert "DEP-001" in rule_ids
        assert "AUTH-005" in rule_ids
        assert "SEC-002" in rule_ids

        # Results
        assert len(run["results"]) == 5

        # Invocations
        assert run["invocations"][0]["executionSuccessful"] is True

    def test_sarif_output_to_file(self, tmp_path):
        """Verifica que el output SARIF se puede escribir a archivo."""
        result = _make_sample_result()
        formatter = SarifFormatter()
        output = formatter.format(result)
        sarif_file = tmp_path / "report.sarif"
        sarif_file.write_text(output, encoding="utf-8")
        # Re-parse from file
        data = json.loads(sarif_file.read_text())
        assert data["version"] == "2.1.0"


# ═══════════════════════════════════════════════════════════
# Summary — FASE 4 improvements
# ═══════════════════════════════════════════════════════════


class TestSummaryByFile:
    """Tests para by_file stats en summary."""

    def test_by_file_present(self):
        result = _make_sample_result()
        summary = build_summary(result)
        assert "by_file" in summary

    def test_by_file_counts_correct(self):
        findings = [
            _make_finding(file="src/main.py"),
            _make_finding(file="src/main.py"),
            _make_finding(file="src/auth.py"),
        ]
        result = ScanResult(findings=findings, files_scanned=5)
        summary = build_summary(result)
        assert summary["by_file"]["src/main.py"] == 2
        assert summary["by_file"]["src/auth.py"] == 1

    def test_by_file_sorted_by_count(self):
        findings = [
            _make_finding(file="a.py"),
            _make_finding(file="b.py"),
            _make_finding(file="b.py"),
            _make_finding(file="b.py"),
            _make_finding(file="c.py"),
            _make_finding(file="c.py"),
        ]
        result = ScanResult(findings=findings, files_scanned=3)
        summary = build_summary(result)
        files_list = list(summary["by_file"].keys())
        assert files_list[0] == "b.py"  # 3 findings

    def test_by_file_max_10(self):
        """by_file se limita a los top 10 archivos."""
        findings = [_make_finding(file=f"file_{i}.py") for i in range(20)]
        result = ScanResult(findings=findings, files_scanned=20)
        summary = build_summary(result)
        assert len(summary["by_file"]) <= 10

    def test_by_file_empty_when_no_findings(self):
        result = ScanResult(files_scanned=10)
        summary = build_summary(result)
        assert summary["by_file"] == {}


# ═══════════════════════════════════════════════════════════
# get_formatter factory — FASE 4 improvements
# ═══════════════════════════════════════════════════════════


class TestGetFormatterKwargs:
    """Tests para kwargs en get_formatter factory."""

    def test_human_with_kwargs(self):
        formatter = get_formatter("human", colors=False, quiet=True)
        assert isinstance(formatter, HumanFormatter)
        assert formatter._colors is False
        assert formatter._quiet is True

    def test_human_with_show_suggestions(self):
        formatter = get_formatter("human", show_suggestions=False)
        assert isinstance(formatter, HumanFormatter)
        assert formatter._show_suggestions is False

    def test_json_ignores_kwargs(self):
        """JSON formatter ignores extra kwargs without error."""
        formatter = get_formatter("json", colors=False)
        assert isinstance(formatter, JsonFormatter)

    def test_sarif_ignores_kwargs(self):
        formatter = get_formatter("sarif", quiet=True)
        assert isinstance(formatter, SarifFormatter)

    def test_junit_ignores_kwargs(self):
        formatter = get_formatter("junit", show_suggestions=False)
        assert isinstance(formatter, JunitFormatter)


# ═══════════════════════════════════════════════════════════
# Edge cases — caracteres especiales, archivos vacios, etc.
# ═══════════════════════════════════════════════════════════


class TestFormatterEdgeCases:
    """Edge cases comunes a todos los formatters."""

    def test_empty_result_all_formatters(self):
        """Todos los formatters manejan ScanResult vacio."""
        result = ScanResult()
        for fmt_name in ("human", "json", "junit", "sarif"):
            formatter = get_formatter(fmt_name)
            output = formatter.format(result)
            assert output  # Non-empty output

    def test_finding_with_windows_path(self):
        """Paths Windows no causan problemas."""
        finding = _make_finding(file="src\\main\\app.py")
        result = ScanResult(findings=[finding])
        for fmt_name in ("human", "json", "junit", "sarif"):
            formatter = get_formatter(fmt_name)
            output = formatter.format(result)
            assert "app.py" in output

    def test_finding_with_unicode_message(self):
        """Mensajes con Unicode se formatean sin error."""
        finding = _make_finding()
        finding.message = "Paquete 'test' no existe — verificar el registro público"
        result = ScanResult(findings=[finding])
        for fmt_name in ("human", "json", "junit", "sarif"):
            formatter = get_formatter(fmt_name)
            output = formatter.format(result)
            assert "verificar" in output

    def test_finding_with_empty_suggestion(self):
        """Suggestion vacia (string vacio) no causa crash."""
        finding = _make_finding(suggestion="")
        result = ScanResult(findings=[finding])
        for fmt_name in ("human", "json", "junit", "sarif"):
            formatter = get_formatter(fmt_name)
            output = formatter.format(result)
            assert output

    def test_very_long_message(self):
        """Mensajes muy largos no causan problemas."""
        finding = _make_finding()
        finding.message = "x" * 10000
        result = ScanResult(findings=[finding])
        for fmt_name in ("human", "json", "junit", "sarif"):
            formatter = get_formatter(fmt_name)
            output = formatter.format(result)
            assert output

    def test_metadata_with_non_serializable(self):
        """JSON formatter handles non-serializable metadata gracefully."""
        from pathlib import Path
        finding = _make_finding()
        finding.metadata = {"path": Path("/tmp/test")}
        result = ScanResult(findings=[finding])
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["findings"][0]["metadata"]["path"] is not None
