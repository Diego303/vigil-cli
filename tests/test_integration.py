"""Integration tests — end-to-end scan con engine, config, y formatters."""

import json

import pytest

from vigil.config.schema import RuleOverride, ScanConfig
from vigil.core.engine import ScanEngine, ScanResult
from vigil.core.finding import Category, Finding, Location, Severity
from vigil.reports.formatter import get_formatter
from vigil.reports.summary import build_summary


class FakeAnalyzer:
    """Analyzer falso configurable para integration tests."""

    def __init__(self, name: str, category: Category, findings: list[Finding]):
        self._name = name
        self.category = category
        self._findings = findings

    @property
    def name(self) -> str:
        return self._name

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        return self._findings


def _make_findings() -> list[Finding]:
    """Crea un conjunto realista de findings para integration tests."""
    return [
        Finding(
            rule_id="DEP-001",
            category=Category.DEPENDENCY,
            severity=Severity.CRITICAL,
            message="Package 'python-jwt-utils' does not exist in pypi.",
            location=Location(file="requirements.txt", line=14),
            suggestion="Remove 'python-jwt-utils' and find the correct package name.",
            metadata={"package": "python-jwt-utils", "ecosystem": "pypi"},
        ),
        Finding(
            rule_id="SEC-006",
            category=Category.SECRETS,
            severity=Severity.CRITICAL,
            message="Value 'your-api-key-here' appears copied from .env.example.",
            location=Location(
                file="src/auth/config.py", line=23,
                snippet='API_KEY = "your-api-key-here"',
            ),
            suggestion="Use os.environ.get('API_KEY') instead of hardcoding.",
        ),
        Finding(
            rule_id="AUTH-005",
            category=Category.AUTH,
            severity=Severity.HIGH,
            message="CORS configured with '*' allowing requests from any origin.",
            location=Location(file="src/main.py", line=8),
            suggestion="Restrict CORS to specific trusted origins.",
        ),
        Finding(
            rule_id="TEST-001",
            category=Category.TEST_QUALITY,
            severity=Severity.HIGH,
            message="Test 'test_login_success' has no assertions.",
            location=Location(file="tests/test_auth.py", line=45),
            suggestion="Add at least one assert to verify the expected behavior.",
        ),
        Finding(
            rule_id="AUTH-003",
            category=Category.AUTH,
            severity=Severity.MEDIUM,
            message="JWT with lifetime of 72 hours (exceeds 24h threshold).",
            location=Location(
                file="src/auth/jwt.py", line=31,
                snippet='expiresIn: "72h"',
            ),
            suggestion="Reduce token lifetime or use refresh tokens.",
        ),
    ]


class TestEndToEndScan:
    def test_full_scan_with_findings(self, tmp_path):
        """Simula un scan completo con findings de multiples categorias."""
        (tmp_path / "app.py").write_text("from flask import Flask")
        (tmp_path / "requirements.txt").write_text("flask==3.0.0")

        config = ScanConfig()
        engine = ScanEngine(config)

        all_findings = _make_findings()
        dep_findings = [f for f in all_findings if f.category == Category.DEPENDENCY]
        auth_findings = [f for f in all_findings if f.category == Category.AUTH]
        sec_findings = [f for f in all_findings if f.category == Category.SECRETS]
        test_findings = [f for f in all_findings if f.category == Category.TEST_QUALITY]

        engine.register_analyzer(
            FakeAnalyzer("dependency", Category.DEPENDENCY, dep_findings)
        )
        engine.register_analyzer(
            FakeAnalyzer("auth", Category.AUTH, auth_findings)
        )
        engine.register_analyzer(
            FakeAnalyzer("secrets", Category.SECRETS, sec_findings)
        )
        engine.register_analyzer(
            FakeAnalyzer("test-quality", Category.TEST_QUALITY, test_findings)
        )

        result = engine.run([str(tmp_path)])

        # Verificar que todos los findings estan presentes
        assert len(result.findings) == 5
        assert result.files_scanned >= 1

        # Verificar orden por severidad
        severities = [f.severity for f in result.findings]
        severity_order = [
            Severity.CRITICAL, Severity.CRITICAL,
            Severity.HIGH, Severity.HIGH,
            Severity.MEDIUM,
        ]
        assert severities == severity_order

        # Verificar que todos los analyzers corrieron
        assert set(result.analyzers_run) == {
            "dependency", "auth", "secrets", "test-quality"
        }

    def test_scan_with_rule_disable(self, tmp_path):
        """Desabilitar una regla la quita de los resultados."""
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(
            rules={"DEP-001": RuleOverride(enabled=False)}
        )
        engine = ScanEngine(config)
        engine.register_analyzer(
            FakeAnalyzer("dep", Category.DEPENDENCY, _make_findings()[:1])
        )
        result = engine.run([str(tmp_path)])
        assert len(result.findings) == 0

    def test_scan_with_exclude_rule(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(exclude_rules=["AUTH-003"])
        engine = ScanEngine(config)
        engine.register_analyzer(
            FakeAnalyzer("auth", Category.AUTH, _make_findings()[2:5])
        )
        result = engine.run([str(tmp_path)])
        assert not any(f.rule_id == "AUTH-003" for f in result.findings)

    def test_scan_with_severity_override(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(
            rules={"AUTH-005": RuleOverride(severity="low")}
        )
        engine = ScanEngine(config)
        engine.register_analyzer(
            FakeAnalyzer("auth", Category.AUTH, [_make_findings()[2]])
        )
        result = engine.run([str(tmp_path)])
        assert result.findings[0].severity == Severity.LOW

    def test_scan_with_category_filter(self, tmp_path):
        """Solo los analyzers de la categoria filtrada corren."""
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(categories=["dependency"])
        engine = ScanEngine(config)
        engine.register_analyzer(
            FakeAnalyzer("dep", Category.DEPENDENCY, _make_findings()[:1])
        )
        engine.register_analyzer(
            FakeAnalyzer("auth", Category.AUTH, _make_findings()[2:4])
        )
        result = engine.run([str(tmp_path)])
        assert "dep" in result.analyzers_run
        assert "auth" not in result.analyzers_run


class TestFormatterIntegration:
    """Verifica que los formatters producen output valido con datos reales."""

    @pytest.fixture
    def scan_result(self) -> ScanResult:
        return ScanResult(
            findings=_make_findings(),
            files_scanned=42,
            duration_seconds=1.234,
            analyzers_run=["dependency", "auth", "secrets", "test-quality"],
        )

    def test_human_format_complete(self, scan_result):
        formatter = get_formatter("human")
        output = formatter.format(scan_result)
        assert "vigil" in output
        assert "42 files" in output
        assert "5 findings" in output
        assert "DEP-001" in output
        assert "SEC-006" in output
        assert "AUTH-005" in output
        assert "TEST-001" in output
        assert "AUTH-003" in output

    def test_json_format_complete(self, scan_result):
        formatter = get_formatter("json")
        output = formatter.format(scan_result)
        data = json.loads(output)
        assert data["files_scanned"] == 42
        assert data["findings_count"] == 5
        assert len(data["findings"]) == 5
        # Verificar que cada finding tiene los campos requeridos
        for f in data["findings"]:
            assert "rule_id" in f
            assert "category" in f
            assert "severity" in f
            assert "message" in f
            assert "location" in f
            assert "file" in f["location"]

    def test_sarif_format_complete(self, scan_result):
        formatter = get_formatter("sarif")
        output = formatter.format(scan_result)
        data = json.loads(output)
        assert data["version"] == "2.1.0"
        run = data["runs"][0]
        assert len(run["results"]) == 5
        # Verificar que las reglas usadas estan definidas
        rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
        finding_rule_ids = {r["ruleId"] for r in run["results"]}
        assert finding_rule_ids.issubset(rule_ids)

    def test_junit_format_complete(self, scan_result):
        import xml.etree.ElementTree as ET
        formatter = get_formatter("junit")
        output = formatter.format(scan_result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert suite.get("failures") == "5"
        testcases = suite.findall("testcase")
        assert len(testcases) == 5

    def test_summary_complete(self, scan_result):
        summary = build_summary(scan_result)
        assert summary["total_findings"] == 5
        assert summary["by_severity"]["critical"] == 2
        assert summary["by_severity"]["high"] == 2
        assert summary["by_severity"]["medium"] == 1
        assert summary["by_category"]["dependency"] == 1
        assert summary["by_category"]["auth"] == 2
        assert summary["by_category"]["secrets"] == 1
        assert summary["by_category"]["test-quality"] == 1
        assert summary["has_blocking"] is True


class TestFindingsAboveThreshold:
    """Verifica que findings_above funciona correctamente con todos los thresholds."""

    @pytest.fixture
    def result(self) -> ScanResult:
        return ScanResult(findings=_make_findings())

    def test_critical_threshold(self, result):
        above = result.findings_above(Severity.CRITICAL)
        assert len(above) == 2
        assert all(f.severity == Severity.CRITICAL for f in above)

    def test_high_threshold(self, result):
        above = result.findings_above(Severity.HIGH)
        assert len(above) == 4  # 2 CRITICAL + 2 HIGH

    def test_medium_threshold(self, result):
        above = result.findings_above(Severity.MEDIUM)
        assert len(above) == 5  # 2 CRITICAL + 2 HIGH + 1 MEDIUM

    def test_low_threshold(self, result):
        above = result.findings_above(Severity.LOW)
        assert len(above) == 5  # All >= LOW

    def test_info_threshold(self, result):
        above = result.findings_above(Severity.INFO)
        assert len(above) == 5  # All >= INFO
