"""Tests para ScanEngine y ScanResult."""

import pytest

from vigil.config.schema import RuleOverride, ScanConfig
from vigil.core.engine import ScanEngine, ScanResult
from vigil.core.finding import Category, Finding, Location, Severity


class TestScanResult:
    def test_empty_result(self):
        result = ScanResult()
        assert result.findings == []
        assert result.files_scanned == 0
        assert result.critical_count == 0
        assert result.high_count == 0
        assert result.has_blocking_findings is False

    def test_counts(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.low_count == 1

    def test_has_blocking(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        assert result.has_blocking_findings is True

    def test_no_blocking(self):
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="X-001",
                    category=Category.AUTH,
                    severity=Severity.LOW,
                    message="test",
                    location=Location(file="x"),
                )
            ]
        )
        assert result.has_blocking_findings is False

    def test_findings_above_high(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        above = result.findings_above(Severity.HIGH)
        assert len(above) == 2  # CRITICAL + HIGH

    def test_findings_above_medium(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        above = result.findings_above(Severity.MEDIUM)
        assert len(above) == 3  # CRITICAL + HIGH + MEDIUM

    def test_findings_above_critical(self, sample_findings):
        result = ScanResult(findings=sample_findings)
        above = result.findings_above(Severity.CRITICAL)
        assert len(above) == 1


class FakeAnalyzer:
    """Analyzer falso para testing."""

    def __init__(self, name: str, findings: list[Finding] | None = None, error: Exception | None = None):
        self._name = name
        self._findings = findings or []
        self._error = error
        self.category = Category.DEPENDENCY

    @property
    def name(self) -> str:
        return self._name

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        if self._error:
            raise self._error
        return self._findings


class TestScanEngine:
    def test_run_no_analyzers(self, tmp_path, default_config):
        (tmp_path / "test.py").write_text("print('hello')")
        engine = ScanEngine(default_config)
        result = engine.run([str(tmp_path)])
        assert result.files_scanned >= 1
        assert result.findings == []
        assert result.analyzers_run == []
        assert result.duration_seconds > 0

    def test_run_with_analyzer(self, tmp_path, default_config):
        (tmp_path / "test.py").write_text("import os")
        finding = Finding(
            rule_id="DEP-001",
            category=Category.DEPENDENCY,
            severity=Severity.CRITICAL,
            message="Package does not exist.",
            location=Location(file="requirements.txt", line=1),
        )
        analyzer = FakeAnalyzer("test-analyzer", findings=[finding])

        engine = ScanEngine(default_config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "DEP-001"
        assert "test-analyzer" in result.analyzers_run

    def test_analyzer_error_doesnt_crash(self, tmp_path, default_config):
        (tmp_path / "test.py").write_text("x = 1")
        error_analyzer = FakeAnalyzer(
            "broken-analyzer", error=RuntimeError("boom")
        )
        engine = ScanEngine(default_config)
        engine.register_analyzer(error_analyzer)
        result = engine.run([str(tmp_path)])

        assert len(result.errors) == 1
        assert "boom" in result.errors[0]
        assert result.analyzers_run == []

    def test_findings_sorted_by_severity(self, tmp_path, default_config):
        (tmp_path / "test.py").write_text("x = 1")
        findings = [
            Finding(
                rule_id="X-001", category=Category.AUTH,
                severity=Severity.LOW, message="low",
                location=Location(file="a"),
            ),
            Finding(
                rule_id="X-002", category=Category.AUTH,
                severity=Severity.CRITICAL, message="critical",
                location=Location(file="a"),
            ),
            Finding(
                rule_id="X-003", category=Category.AUTH,
                severity=Severity.MEDIUM, message="medium",
                location=Location(file="a"),
            ),
        ]
        analyzer = FakeAnalyzer("test", findings=findings)
        engine = ScanEngine(default_config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        assert result.findings[0].severity == Severity.CRITICAL
        assert result.findings[1].severity == Severity.MEDIUM
        assert result.findings[2].severity == Severity.LOW

    def test_rule_override_disable(self, tmp_path):
        config = ScanConfig(
            rules={"DEP-001": RuleOverride(enabled=False)}
        )
        (tmp_path / "test.py").write_text("x = 1")
        finding = Finding(
            rule_id="DEP-001", category=Category.DEPENDENCY,
            severity=Severity.CRITICAL, message="test",
            location=Location(file="x"),
        )
        analyzer = FakeAnalyzer("test", findings=[finding])
        engine = ScanEngine(config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        assert len(result.findings) == 0

    def test_rule_override_severity(self, tmp_path):
        config = ScanConfig(
            rules={"DEP-001": RuleOverride(severity="low")}
        )
        (tmp_path / "test.py").write_text("x = 1")
        finding = Finding(
            rule_id="DEP-001", category=Category.DEPENDENCY,
            severity=Severity.CRITICAL, message="test",
            location=Location(file="x"),
        )
        analyzer = FakeAnalyzer("test", findings=[finding])
        engine = ScanEngine(config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.LOW

    def test_exclude_rules(self, tmp_path):
        config = ScanConfig(exclude_rules=["AUTH-005"])
        (tmp_path / "test.py").write_text("x = 1")
        findings = [
            Finding(
                rule_id="DEP-001", category=Category.DEPENDENCY,
                severity=Severity.CRITICAL, message="dep",
                location=Location(file="x"),
            ),
            Finding(
                rule_id="AUTH-005", category=Category.AUTH,
                severity=Severity.HIGH, message="auth",
                location=Location(file="x"),
            ),
        ]
        analyzer = FakeAnalyzer("test", findings=findings)
        engine = ScanEngine(config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "DEP-001"

    def test_category_filter(self, tmp_path):
        config = ScanConfig(categories=["auth"])
        (tmp_path / "test.py").write_text("x = 1")

        dep_analyzer = FakeAnalyzer("dep-analyzer")
        dep_analyzer.category = Category.DEPENDENCY

        auth_analyzer = FakeAnalyzer(
            "auth-analyzer",
            findings=[
                Finding(
                    rule_id="AUTH-001", category=Category.AUTH,
                    severity=Severity.HIGH, message="auth issue",
                    location=Location(file="x"),
                )
            ],
        )
        auth_analyzer.category = Category.AUTH

        engine = ScanEngine(config)
        engine.register_analyzer(dep_analyzer)
        engine.register_analyzer(auth_analyzer)
        result = engine.run([str(tmp_path)])

        assert "auth-analyzer" in result.analyzers_run
        assert "dep-analyzer" not in result.analyzers_run
