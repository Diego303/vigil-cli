"""Tests para todos los formatters de output."""

import json
import xml.etree.ElementTree as ET

from vigil.core.engine import ScanResult
from vigil.core.finding import Category, Finding, Location, Severity
from vigil.reports.formatter import get_formatter
from vigil.reports.human import HumanFormatter
from vigil.reports.json_fmt import JsonFormatter
from vigil.reports.junit import JunitFormatter
from vigil.reports.sarif import SarifFormatter
from vigil.reports.summary import build_summary


class TestGetFormatter:
    def test_human(self):
        f = get_formatter("human")
        assert isinstance(f, HumanFormatter)

    def test_json(self):
        f = get_formatter("json")
        assert isinstance(f, JsonFormatter)

    def test_junit(self):
        f = get_formatter("junit")
        assert isinstance(f, JunitFormatter)

    def test_sarif(self):
        f = get_formatter("sarif")
        assert isinstance(f, SarifFormatter)

    def test_unknown_format(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown format"):
            get_formatter("xml")


class TestHumanFormatter:
    def test_empty_result(self):
        result = ScanResult(files_scanned=10, duration_seconds=0.5)
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "10 files" in output
        assert "0 findings" in output
        assert "No findings" in output

    def test_with_findings(self, sample_findings):
        result = ScanResult(
            findings=sample_findings,
            files_scanned=42,
            duration_seconds=1.2,
            analyzers_run=["dependency", "auth"],
        )
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "42 files" in output
        assert "DEP-001" in output
        assert "AUTH-005" in output
        assert "dependency" in output

    def test_with_errors(self):
        result = ScanResult(
            files_scanned=5,
            errors=["Analyzer failed: timeout"],
        )
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "Analyzer failed" in output

    def test_suggestion_shown(self, sample_finding):
        result = ScanResult(findings=[sample_finding], files_scanned=1)
        formatter = HumanFormatter()
        output = formatter.format(result)
        assert "Suggestion" in output


class TestJsonFormatter:
    def test_empty_result(self):
        result = ScanResult(files_scanned=5, duration_seconds=0.1)
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["files_scanned"] == 5
        assert data["findings_count"] == 0
        assert data["findings"] == []

    def test_with_findings(self, sample_findings):
        result = ScanResult(
            findings=sample_findings,
            files_scanned=10,
            analyzers_run=["dep", "auth"],
        )
        formatter = JsonFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["findings_count"] == 4
        assert data["findings"][0]["rule_id"] == "DEP-001"
        assert data["findings"][0]["severity"] == "critical"
        assert data["findings"][0]["location"]["file"] == "requirements.txt"

    def test_valid_json(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        formatter = JsonFormatter()
        output = formatter.format(result)
        # Should not raise
        json.loads(output)


class TestJunitFormatter:
    def test_empty_result(self):
        result = ScanResult(files_scanned=5, duration_seconds=0.5)
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("failures") == "0"
        assert suite.get("tests") == "1"

    def test_with_findings(self, sample_findings):
        result = ScanResult(findings=sample_findings, files_scanned=10)
        formatter = JunitFormatter()
        output = formatter.format(result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("failures") == "4"
        testcases = suite.findall("testcase")
        assert len(testcases) == 4

    def test_valid_xml(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        formatter = JunitFormatter()
        output = formatter.format(result)
        # Should not raise
        ET.fromstring(output)


class TestSarifFormatter:
    def test_empty_result(self):
        result = ScanResult(files_scanned=5)
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert data["version"] == "2.1.0"
        assert data["runs"][0]["results"] == []

    def test_with_findings(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        run = data["runs"][0]
        assert len(run["results"]) == 4
        assert run["results"][0]["ruleId"] == "DEP-001"
        assert run["results"][0]["level"] == "error"

    def test_sarif_schema_present(self):
        result = ScanResult()
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        assert "$schema" in data
        assert "2.1.0" in data["$schema"]

    def test_tool_info(self):
        result = ScanResult()
        formatter = SarifFormatter()
        output = formatter.format(result)
        data = json.loads(output)
        driver = data["runs"][0]["tool"]["driver"]
        assert driver["name"] == "vigil"
        assert driver["version"] == "0.1.0"


class TestSummary:
    def test_empty_summary(self):
        result = ScanResult(files_scanned=10, duration_seconds=0.5)
        summary = build_summary(result)
        assert summary["files_scanned"] == 10
        assert summary["total_findings"] == 0
        assert summary["by_severity"] == {}
        assert summary["by_category"] == {}
        assert summary["has_blocking"] is False

    def test_summary_with_findings(self, sample_findings):
        result = ScanResult(
            findings=sample_findings,
            files_scanned=42,
            duration_seconds=1.5,
            analyzers_run=["dep", "auth"],
        )
        summary = build_summary(result)
        assert summary["total_findings"] == 4
        assert summary["by_severity"]["critical"] == 1
        assert summary["by_severity"]["high"] == 1
        assert summary["by_category"]["dependency"] == 1
        assert summary["by_category"]["auth"] == 2
        assert summary["has_blocking"] is True
