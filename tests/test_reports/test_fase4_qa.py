"""QA Tests FASE 4 — Regression, edge cases, integration, false positive/negative.

Covers:
- Regression tests for bugs fixed in QA audit
- Edge cases: empty strings, None values, extreme sizes, special characters
- False positives: legitimate code that should NOT cause formatter errors
- Integration: cross-formatter consistency, CLI formatter wiring
- Configuration: formatter options combinations
"""

import json
import xml.etree.ElementTree as ET

import pytest

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
    suggestion: str | None = None,
    snippet: str | None = None,
    column: int | None = None,
    end_line: int | None = None,
    message: str | None = None,
    metadata: dict | None = None,
) -> Finding:
    f = Finding(
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
    if metadata:
        f.metadata = metadata
    return f


# ═══════════════════════════════════════════════════════════
# REGRESSION TESTS — bugs found during QA audit
# ═══════════════════════════════════════════════════════════


class TestRegressionHumanNoFindingsWithErrors:
    """Regression: human.py showed "No findings." even when errors existed."""

    def test_no_findings_message_hidden_when_errors_exist(self):
        """BUG FIX: 'No findings.' must NOT appear when there are analyzer errors."""
        result = ScanResult(errors=["Analyzer X failed: timeout"])
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "No findings." not in output
        assert "Analyzer X failed" in output

    def test_no_findings_message_shown_when_clean(self):
        """'No findings.' should still appear when no findings AND no errors."""
        result = ScanResult(files_scanned=10)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "No findings." in output

    def test_no_findings_with_errors_quiet_mode(self):
        """In quiet mode, errors still shown but no 'No findings.' message."""
        result = ScanResult(errors=["Error 1"])
        formatter = HumanFormatter(quiet=True, colors=False)
        output = formatter.format(result)
        assert "No findings." not in output
        assert "Error 1" in output

    def test_findings_and_errors_both_shown(self):
        """When both findings and errors exist, both sections visible."""
        finding = _make_finding()
        result = ScanResult(findings=[finding], errors=["Analyzer Y crashed"])
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "DEP-001" in output
        assert "Analyzer Y crashed" in output


class TestRegressionSarifRuleIndex:
    """Regression: sarif.py used .get(rule_id, 0) which masks missing keys."""

    def test_rule_index_all_findings_have_valid_index(self):
        """Every finding's rule_id must exist in rule_index_map."""
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
            _make_finding("SEC-002", category=Category.SECRETS),
        ]
        result = ScanResult(findings=findings)
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        results = data["runs"][0]["results"]

        # Each ruleIndex must be a valid index into rules array
        for sarif_result in results:
            idx = sarif_result["ruleIndex"]
            assert 0 <= idx < len(rules), (
                f"ruleIndex {idx} out of range for {sarif_result['ruleId']}"
            )
            # ruleIndex must point to the correct rule
            assert rules[idx]["id"] == sarif_result["ruleId"]

    def test_duplicate_rule_ids_share_index(self):
        """Multiple findings with same rule_id share one ruleIndex."""
        findings = [
            _make_finding("DEP-001"),
            _make_finding("DEP-001"),
            _make_finding("DEP-001"),
        ]
        result = ScanResult(findings=findings)
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        results = data["runs"][0]["results"]
        indices = {r["ruleIndex"] for r in results}
        assert len(indices) == 1  # All same index


class TestRegressionJunitTestsCount:
    """Regression: junit.py tests attribute didn't include error testcases."""

    def test_tests_count_includes_errors(self):
        """tests attribute = findings + errors count."""
        result = ScanResult(
            findings=[_make_finding()],
            errors=["Analyzer X failed"],
        )
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        tests = int(suite.get("tests"))
        failures = int(suite.get("failures"))
        errors = int(suite.get("errors"))
        assert tests == failures + errors  # 1 + 1 = 2

    def test_tests_count_only_errors(self):
        """When only errors (no findings), tests count still correct."""
        result = ScanResult(errors=["Error 1", "Error 2"])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("tests") == "2"
        assert suite.get("failures") == "0"
        assert suite.get("errors") == "2"

    def test_tests_count_no_findings_no_errors(self):
        """Empty scan still has tests=1 (the success testcase)."""
        result = ScanResult()
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("tests") == "1"

    def test_tests_count_many_findings_and_errors(self):
        """Counts match total testcase elements in XML."""
        findings = [_make_finding(rule_id=f"DEP-{i:03d}") for i in range(5)]
        result = ScanResult(findings=findings, errors=["Err1", "Err2"])
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("tests") == "7"  # 5 findings + 2 errors
        testcases = suite.findall("testcase")
        assert len(testcases) == 7


class TestRegressionSarifDoubleRegistryLookup:
    """Regression: sarif.py called registry.get(rid) twice per rule."""

    def test_all_known_rules_appear_in_sarif(self):
        """Every known rule_id in findings generates a rule entry."""
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-001", category=Category.AUTH),
            _make_finding("SEC-001", category=Category.SECRETS),
            _make_finding("TEST-001", category=Category.TEST_QUALITY),
        ]
        result = ScanResult(findings=findings)
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert rule_ids == {"DEP-001", "AUTH-001", "SEC-001", "TEST-001"}


# ═══════════════════════════════════════════════════════════
# EDGE CASES — extreme inputs, boundary conditions
# ═══════════════════════════════════════════════════════════


class TestEdgeCasesAllFormatters:
    """Edge cases applied across all 4 formatters."""

    ALL_FORMATS = ("human", "json", "junit", "sarif")

    def test_zero_duration(self):
        """duration_seconds=0 doesn't cause division errors."""
        result = ScanResult(files_scanned=1, duration_seconds=0.0)
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_negative_duration(self):
        """Negative duration (clock skew) doesn't crash."""
        result = ScanResult(duration_seconds=-0.5)
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_very_large_files_scanned(self):
        """Huge files_scanned number doesn't cause issues."""
        result = ScanResult(files_scanned=999999)
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_finding_with_zero_line(self):
        """Line number 0 is handled (some tools use 0-based indexing)."""
        finding = _make_finding(line=0)
        result = ScanResult(findings=[finding])
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_finding_with_empty_file_path(self):
        """Empty file path doesn't crash."""
        finding = _make_finding(file="")
        result = ScanResult(findings=[finding])
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_finding_with_newlines_in_message(self):
        """Newlines in message don't break XML/JSON structure."""
        finding = _make_finding()
        finding.message = "Line 1\nLine 2\nLine 3"
        result = ScanResult(findings=[finding])
        # JSON must parse
        json_out = JsonFormatter().format(result)
        data = json.loads(json_out)
        assert "Line 1" in data["findings"][0]["message"]
        # JUnit XML must parse
        junit_out = JunitFormatter().format(result)
        ET.fromstring(junit_out)
        # SARIF must parse
        sarif_out = SarifFormatter().format(result)
        json.loads(sarif_out)

    def test_finding_with_newlines_in_snippet(self):
        """Multi-line snippet doesn't break output."""
        finding = _make_finding(snippet="line1\nline2\nline3", line=1)
        result = ScanResult(findings=[finding])
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_finding_with_tab_characters(self):
        """Tab characters in snippet/message don't break output."""
        finding = _make_finding(snippet="\tindented\tcode")
        finding.message = "Has\ttabs"
        result = ScanResult(findings=[finding])
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_empty_error_string(self):
        """Empty string in errors list doesn't crash."""
        result = ScanResult(errors=[""])
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output

    def test_finding_all_none_optional_fields(self):
        """Finding with all optional fields as None."""
        finding = Finding(
            rule_id="DEP-001",
            category=Category.DEPENDENCY,
            severity=Severity.CRITICAL,
            message="Test",
            location=Location(file="f.py"),
            suggestion=None,
        )
        result = ScanResult(findings=[finding])
        for fmt in self.ALL_FORMATS:
            formatter = get_formatter(fmt)
            output = formatter.format(result)
            assert output


class TestEdgeCasesPascalCase:
    """Edge cases for _to_pascal_case."""

    def test_multiple_spaces(self):
        assert _to_pascal_case("a  b   c") == "ABC"

    def test_leading_trailing_separators(self):
        assert _to_pascal_case("-hello-world-") == "HelloWorld"

    def test_mixed_separators(self):
        assert _to_pascal_case("hello-world_foo bar") == "HelloWorldFooBar"

    def test_numbers_in_words(self):
        assert _to_pascal_case("step 1 check") == "Step1Check"

    def test_already_pascal_case(self):
        assert _to_pascal_case("AlreadyPascal") == "Alreadypascal"


class TestEdgeCasesSummary:
    """Edge cases for build_summary."""

    def test_all_findings_same_file(self):
        """All findings in one file → by_file has single entry."""
        findings = [_make_finding(file="same.py") for _ in range(5)]
        result = ScanResult(findings=findings, files_scanned=1)
        summary = build_summary(result)
        assert summary["by_file"] == {"same.py": 5}

    def test_all_findings_same_severity(self):
        """All same severity → by_severity has single entry."""
        findings = [_make_finding(severity=Severity.HIGH) for _ in range(3)]
        result = ScanResult(findings=findings)
        summary = build_summary(result)
        assert summary["by_severity"] == {"high": 3}

    def test_all_categories_present(self):
        """One finding per category → all 4 in by_category."""
        findings = [
            _make_finding(category=Category.DEPENDENCY),
            _make_finding(category=Category.AUTH),
            _make_finding(category=Category.SECRETS),
            _make_finding(category=Category.TEST_QUALITY),
        ]
        result = ScanResult(findings=findings)
        summary = build_summary(result)
        assert len(summary["by_category"]) == 4

    def test_by_file_exactly_10(self):
        """When exactly 10 unique files, all included."""
        findings = [_make_finding(file=f"f{i}.py") for i in range(10)]
        result = ScanResult(findings=findings)
        summary = build_summary(result)
        assert len(summary["by_file"]) == 10

    def test_by_file_11_files_drops_least(self):
        """When 11 unique files (1 finding each), only top 10 kept."""
        findings = [_make_finding(file=f"f{i}.py") for i in range(11)]
        result = ScanResult(findings=findings)
        summary = build_summary(result)
        assert len(summary["by_file"]) == 10

    def test_duration_already_rounded(self):
        """Duration with exactly 3 decimals stays unchanged."""
        result = ScanResult(duration_seconds=1.234)
        summary = build_summary(result)
        assert summary["duration_seconds"] == 1.234


# ═══════════════════════════════════════════════════════════
# FALSE POSITIVES — things that should NOT cause errors
# ═══════════════════════════════════════════════════════════


class TestFalsePositivesSarifUnknownRuleId:
    """Rule IDs not in RULES_V0 shouldn't crash SARIF formatter."""

    def test_custom_rule_id_not_in_registry(self):
        """Finding with a rule_id not in RULES_V0 still generates valid SARIF."""
        finding = _make_finding(rule_id="CUSTOM-999")
        result = ScanResult(findings=[finding])
        formatter = SarifFormatter()
        data = json.loads(formatter.format(result))
        results = data["runs"][0]["results"]
        assert len(results) == 1
        assert results[0]["ruleId"] == "CUSTOM-999"
        # Unknown rules are not in driver.rules but result still valid
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert "CUSTOM-999" not in rule_ids


class TestFalsePositivesHumanSpecialChars:
    """Special characters in findings shouldn't break human output."""

    def test_ansi_sequences_in_message(self):
        """ANSI escape sequences in finding message don't confuse colorizer."""
        finding = _make_finding()
        finding.message = "Contains \033[91mred\033[0m text"
        result = ScanResult(findings=[finding])
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "Contains" in output

    def test_percent_in_message(self):
        """% characters don't trigger string formatting."""
        finding = _make_finding()
        finding.message = "100% coverage is %s required"
        result = ScanResult(findings=[finding])
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "100%" in output


# ═══════════════════════════════════════════════════════════
# INTEGRATION — cross-formatter consistency
# ═══════════════════════════════════════════════════════════


class TestCrossFormatterConsistency:
    """All formatters should agree on the same data."""

    def test_findings_count_consistent(self):
        """All formatters report the same number of findings."""
        findings = [_make_finding(rule_id=f"DEP-{i:03d}") for i in range(3)]
        result = ScanResult(findings=findings, files_scanned=5)

        # JSON
        json_data = json.loads(JsonFormatter().format(result))
        assert json_data["findings_count"] == 3

        # JUnit
        junit_root = ET.fromstring(JunitFormatter().format(result))
        assert junit_root.find("testsuite").get("failures") == "3"

        # SARIF
        sarif_data = json.loads(SarifFormatter().format(result))
        assert len(sarif_data["runs"][0]["results"]) == 3

        # Human
        human_out = HumanFormatter(colors=False).format(result)
        assert "3 findings" in human_out

    def test_rule_ids_consistent(self):
        """All formatters include the same rule IDs."""
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
        ]
        result = ScanResult(findings=findings)

        # JSON
        json_data = json.loads(JsonFormatter().format(result))
        json_ids = {f["rule_id"] for f in json_data["findings"]}

        # SARIF
        sarif_data = json.loads(SarifFormatter().format(result))
        sarif_ids = {r["ruleId"] for r in sarif_data["runs"][0]["results"]}

        # JUnit
        junit_root = ET.fromstring(JunitFormatter().format(result))
        junit_names = {tc.get("name") for tc in junit_root.findall(".//testcase")}

        assert json_ids == sarif_ids == {"DEP-001", "AUTH-005"}
        assert all(any(rid in name for name in junit_names)
                   for rid in ["DEP-001", "AUTH-005"])

    def test_errors_consistent(self):
        """All formatters report errors."""
        result = ScanResult(errors=["Error A", "Error B"])

        # JSON
        json_data = json.loads(JsonFormatter().format(result))
        assert json_data["errors"] == ["Error A", "Error B"]

        # JUnit
        junit_root = ET.fromstring(JunitFormatter().format(result))
        error_elems = junit_root.findall(".//error")
        assert len(error_elems) == 2

        # SARIF
        sarif_data = json.loads(SarifFormatter().format(result))
        notifications = sarif_data["runs"][0]["invocations"][0]["toolExecutionNotifications"]
        assert len(notifications) == 2

        # Human
        human_out = HumanFormatter(colors=False).format(result)
        assert "Error A" in human_out
        assert "Error B" in human_out


class TestFormatterOutputValidity:
    """Validate structural correctness of each format output."""

    def _sample_result(self) -> ScanResult:
        return ScanResult(
            findings=[
                _make_finding("DEP-001", suggestion="Fix A", snippet="import x"),
                _make_finding("AUTH-005", Severity.HIGH, Category.AUTH,
                              suggestion="Fix B"),
            ],
            files_scanned=10,
            duration_seconds=2.5,
            analyzers_run=["dependency", "auth"],
            errors=["Warning: slow scan"],
        )

    def test_json_is_valid_json(self):
        data = json.loads(JsonFormatter().format(self._sample_result()))
        assert isinstance(data, dict)
        assert "version" in data
        assert "findings" in data
        assert "summary" in data

    def test_junit_is_valid_xml(self):
        output = JunitFormatter().format(self._sample_result())
        root = ET.fromstring(output)
        assert root.tag == "testsuites"

    def test_sarif_is_valid_sarif_structure(self):
        data = json.loads(SarifFormatter().format(self._sample_result()))
        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert "tool" in run
        assert "results" in run
        assert "invocations" in run

    def test_human_is_non_empty_string(self):
        output = HumanFormatter(colors=False).format(self._sample_result())
        assert isinstance(output, str)
        assert len(output) > 0


# ═══════════════════════════════════════════════════════════
# CONFIGURATION — formatter options combinations
# ═══════════════════════════════════════════════════════════


class TestHumanFormatterOptionsCombinations:
    """Test all meaningful combinations of HumanFormatter options."""

    @pytest.mark.parametrize("colors,quiet,suggestions", [
        (True, True, True),
        (True, True, False),
        (True, False, True),
        (True, False, False),
        (False, True, True),
        (False, True, False),
        (False, False, True),
        (False, False, False),
    ])
    def test_all_option_combos_with_findings(self, colors, quiet, suggestions):
        """All option combinations produce valid output with findings."""
        result = ScanResult(
            findings=[_make_finding(suggestion="Fix it")],
            files_scanned=5,
        )
        formatter = HumanFormatter(
            colors=colors, quiet=quiet, show_suggestions=suggestions,
        )
        output = formatter.format(result)
        assert "DEP-001" in output  # Finding always shown
        if quiet:
            assert "files scanned" not in output
        if not suggestions:
            assert "Suggestion" not in output

    @pytest.mark.parametrize("colors,quiet,suggestions", [
        (True, True, True),
        (True, False, False),
        (False, True, True),
        (False, False, False),
    ])
    def test_option_combos_empty_result(self, colors, quiet, suggestions):
        """All option combinations handle empty results."""
        result = ScanResult(files_scanned=5)
        formatter = HumanFormatter(
            colors=colors, quiet=quiet, show_suggestions=suggestions,
        )
        output = formatter.format(result)
        assert output is not None


class TestGetFormatterUnknown:
    """Factory error handling."""

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown format"):
            get_formatter("yaml")

    def test_error_lists_available_formats(self):
        with pytest.raises(ValueError, match="human"):
            get_formatter("unknown")


# ═══════════════════════════════════════════════════════════
# SARIF-SPECIFIC — schema compliance details
# ═══════════════════════════════════════════════════════════


class TestSarifSchemaCompliance:
    """Detailed SARIF 2.1.0 schema compliance checks."""

    def test_schema_uri_present(self):
        result = ScanResult()
        data = json.loads(SarifFormatter().format(result))
        assert data["$schema"].endswith("sarif-schema-2.1.0.json")

    def test_run_has_required_fields(self):
        result = ScanResult(findings=[_make_finding()])
        data = json.loads(SarifFormatter().format(result))
        run = data["runs"][0]
        assert "tool" in run
        assert "results" in run

    def test_result_has_required_fields(self):
        finding = _make_finding(suggestion="Fix", snippet="code", line=5, column=3)
        result = ScanResult(findings=[finding])
        data = json.loads(SarifFormatter().format(result))
        sarif_result = data["runs"][0]["results"][0]
        assert "ruleId" in sarif_result
        assert "level" in sarif_result
        assert "message" in sarif_result
        assert "locations" in sarif_result

    def test_physical_location_uri_format(self):
        """artifactLocation.uri should be the file path."""
        finding = _make_finding(file="src/main.py")
        result = ScanResult(findings=[finding])
        data = json.loads(SarifFormatter().format(result))
        loc = data["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "src/main.py"

    def test_region_only_when_line_present(self):
        """Region should only exist when line is not None."""
        finding_with_line = _make_finding(line=5)
        finding_no_line = _make_finding(line=None)
        result = ScanResult(findings=[finding_with_line, finding_no_line])
        data = json.loads(SarifFormatter().format(result))
        results = data["runs"][0]["results"]
        assert "region" in results[0]["locations"][0]["physicalLocation"]
        assert "region" not in results[1]["locations"][0]["physicalLocation"]

    def test_fixes_only_when_suggestion_present(self):
        finding_with = _make_finding(suggestion="Fix it")
        finding_without = _make_finding(suggestion=None)
        result = ScanResult(findings=[finding_with, finding_without])
        data = json.loads(SarifFormatter().format(result))
        results = data["runs"][0]["results"]
        assert "fixes" in results[0]
        assert "fixes" not in results[1]

    def test_invocation_successful_without_errors(self):
        result = ScanResult()
        data = json.loads(SarifFormatter().format(result))
        inv = data["runs"][0]["invocations"][0]
        assert inv["executionSuccessful"] is True
        assert inv["toolExecutionNotifications"] == []

    def test_invocation_failed_with_errors(self):
        result = ScanResult(errors=["timeout"])
        data = json.loads(SarifFormatter().format(result))
        inv = data["runs"][0]["invocations"][0]
        assert inv["executionSuccessful"] is False


# ═══════════════════════════════════════════════════════════
# JUNIT-SPECIFIC — XML structure details
# ═══════════════════════════════════════════════════════════


class TestJunitXmlStructure:
    """JUnit XML structure compliance checks."""

    def test_xml_declaration(self):
        result = ScanResult()
        output = JunitFormatter().format(result)
        assert output.startswith("<?xml")

    def test_success_testcase_when_no_findings_no_errors(self):
        """Empty result has a success testcase (vigil-scan)."""
        result = ScanResult()
        output = JunitFormatter().format(result)
        root = ET.fromstring(output)
        testcases = root.findall(".//testcase")
        assert len(testcases) == 1
        assert testcases[0].get("name") == "vigil-scan"
        # No failure or error child
        assert testcases[0].find("failure") is None
        assert testcases[0].find("error") is None

    def test_no_success_testcase_when_findings_exist(self):
        """With findings, no 'vigil-scan' success testcase."""
        result = ScanResult(findings=[_make_finding()])
        output = JunitFormatter().format(result)
        root = ET.fromstring(output)
        names = [tc.get("name") for tc in root.findall(".//testcase")]
        assert "vigil-scan" not in names

    def test_error_testcases_have_error_element(self):
        result = ScanResult(errors=["Err1"])
        output = JunitFormatter().format(result)
        root = ET.fromstring(output)
        error_cases = [
            tc for tc in root.findall(".//testcase")
            if tc.find("error") is not None
        ]
        assert len(error_cases) == 1
        assert error_cases[0].get("name") == "vigil-error"

    def test_failure_message_attribute(self):
        """Failure element has message attribute with finding message."""
        finding = _make_finding(message="Package X not found")
        result = ScanResult(findings=[finding])
        output = JunitFormatter().format(result)
        root = ET.fromstring(output)
        failure = root.find(".//failure")
        assert failure.get("message") == "Package X not found"

    def test_time_format(self):
        """Time attribute uses 3 decimal precision."""
        result = ScanResult(duration_seconds=1.23456)
        output = JunitFormatter().format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("time") == "1.235"


# ═══════════════════════════════════════════════════════════
# JSON-SPECIFIC — output structure details
# ═══════════════════════════════════════════════════════════


class TestJsonOutputStructure:
    """JSON output structure compliance checks."""

    def test_top_level_keys(self):
        result = ScanResult()
        data = json.loads(JsonFormatter().format(result))
        expected_keys = {
            "version", "files_scanned", "duration_seconds",
            "analyzers_run", "findings_count", "findings",
            "summary", "errors",
        }
        assert set(data.keys()) == expected_keys

    def test_finding_keys(self):
        finding = _make_finding(suggestion="Fix", snippet="code")
        result = ScanResult(findings=[finding])
        data = json.loads(JsonFormatter().format(result))
        f = data["findings"][0]
        assert "rule_id" in f
        assert "category" in f
        assert "severity" in f
        assert "message" in f
        assert "location" in f
        assert "suggestion" in f
        assert "metadata" in f

    def test_category_value_is_string(self):
        finding = _make_finding(category=Category.AUTH)
        result = ScanResult(findings=[finding])
        data = json.loads(JsonFormatter().format(result))
        assert data["findings"][0]["category"] == "auth"

    def test_severity_value_is_string(self):
        finding = _make_finding(severity=Severity.MEDIUM)
        result = ScanResult(findings=[finding])
        data = json.loads(JsonFormatter().format(result))
        assert data["findings"][0]["severity"] == "medium"

    def test_duration_rounded_to_3_decimals(self):
        result = ScanResult(duration_seconds=1.23456789)
        data = json.loads(JsonFormatter().format(result))
        assert data["duration_seconds"] == 1.235


# ═══════════════════════════════════════════════════════════
# HUMAN-SPECIFIC — rendering details
# ═══════════════════════════════════════════════════════════


class TestHumanRendering:
    """Human formatter rendering details."""

    def test_severity_uppercase_in_output(self):
        finding = _make_finding(severity=Severity.CRITICAL)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "CRITICAL" in output

    def test_location_with_line(self):
        finding = _make_finding(file="src/app.py", line=42)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "src/app.py:42" in output

    def test_location_without_line(self):
        finding = _make_finding(file="src/app.py", line=None)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "src/app.py" in output
        assert "src/app.py:" not in output

    def test_snippet_shown_with_pipe(self):
        finding = _make_finding(snippet="import os", line=1)
        result = ScanResult(findings=[finding], files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "| import os" in output

    def test_multiple_findings_separated_by_blank_line(self):
        findings = [
            _make_finding("DEP-001"),
            _make_finding("AUTH-005", category=Category.AUTH),
        ]
        result = ScanResult(findings=findings, files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        # Each finding block ends with empty line
        lines = output.split("\n")
        # Find DEP-001 line and AUTH-005 line
        dep_idx = next(i for i, line in enumerate(lines) if "DEP-001" in line)
        auth_idx = next(i for i, line in enumerate(lines) if "AUTH-005" in line)
        # There should be a blank line between them
        assert any(lines[i].strip() == "" for i in range(dep_idx + 1, auth_idx))

    def test_summary_severity_breakdown(self):
        """Summary line shows severity breakdown."""
        findings = [
            _make_finding(severity=Severity.CRITICAL),
            _make_finding(severity=Severity.CRITICAL),
            _make_finding(severity=Severity.LOW),
        ]
        result = ScanResult(findings=findings, files_scanned=1)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "2 critical" in output
        assert "1 low" in output

    def test_summary_0_findings_text(self):
        """Empty scan shows '0 findings' in summary."""
        result = ScanResult(files_scanned=10)
        formatter = HumanFormatter(colors=False)
        output = formatter.format(result)
        assert "0 findings" in output


# ═══════════════════════════════════════════════════════════
# SPECIAL CHARACTERS — XML/JSON escaping
# ═══════════════════════════════════════════════════════════


class TestSpecialCharacterEscaping:
    """Ensure special characters are properly escaped in each format."""

    def test_xml_special_chars_in_junit(self):
        """<, >, &, ', \" in finding don't break JUnit XML."""
        finding = _make_finding()
        finding.message = '<script>alert("xss")</script> & stuff'
        finding.suggestion = 'Use "safe" & <proper> encoding'
        result = ScanResult(findings=[finding])
        output = JunitFormatter().format(result)
        root = ET.fromstring(output)  # Must parse without error
        failure = root.find(".//failure")
        assert failure is not None

    def test_json_special_chars(self):
        """Quotes and backslashes in finding don't break JSON."""
        finding = _make_finding()
        finding.message = 'Path "C:\\Users\\test" has \\n newline'
        result = ScanResult(findings=[finding])
        output = JsonFormatter().format(result)
        data = json.loads(output)  # Must parse without error
        assert "C:\\Users\\test" in data["findings"][0]["message"]

    def test_sarif_special_chars(self):
        """Special characters in SARIF don't break JSON structure."""
        finding = _make_finding()
        finding.message = 'Contains "quotes" and \\backslash\\ and \ttab'
        result = ScanResult(findings=[finding])
        output = SarifFormatter().format(result)
        data = json.loads(output)  # Must parse without error
        assert "quotes" in data["runs"][0]["results"][0]["message"]["text"]

    def test_null_bytes_in_message(self):
        """Null bytes in message don't break formatters."""
        finding = _make_finding()
        finding.message = "Has null\x00byte"
        result = ScanResult(findings=[finding])
        # JSON and SARIF should handle it
        json_out = JsonFormatter().format(result)
        assert json_out  # Non-empty
        # Human should handle it
        human_out = HumanFormatter(colors=False).format(result)
        assert human_out


# ═══════════════════════════════════════════════════════════
# METADATA — complex metadata handling
# ═══════════════════════════════════════════════════════════


class TestMetadataHandling:
    """Tests for complex metadata in findings."""

    def test_nested_dict_metadata(self):
        finding = _make_finding(metadata={"a": {"b": {"c": 1}}})
        result = ScanResult(findings=[finding])
        data = json.loads(JsonFormatter().format(result))
        assert data["findings"][0]["metadata"]["a"]["b"]["c"] == 1

    def test_list_metadata(self):
        finding = _make_finding(metadata={"items": [1, 2, 3]})
        result = ScanResult(findings=[finding])
        data = json.loads(JsonFormatter().format(result))
        assert data["findings"][0]["metadata"]["items"] == [1, 2, 3]

    def test_empty_metadata(self):
        finding = _make_finding(metadata={})
        result = ScanResult(findings=[finding])
        data = json.loads(JsonFormatter().format(result))
        assert data["findings"][0]["metadata"] == {}
