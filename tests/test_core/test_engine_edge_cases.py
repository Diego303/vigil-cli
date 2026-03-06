"""Edge case tests para ScanEngine y ScanResult."""

import pytest

from vigil.config.schema import RuleOverride, ScanConfig
from vigil.core.engine import SEVERITY_SORT_ORDER, ScanEngine, ScanResult
from vigil.core.finding import Category, Finding, Location, Severity


# ── Helpers ──────────────────────────────────────────────────


class FakeAnalyzer:
    def __init__(
        self,
        name: str,
        category: Category = Category.DEPENDENCY,
        findings: list[Finding] | None = None,
        error: Exception | None = None,
    ):
        self._name = name
        self.category = category
        self._findings = findings or []
        self._error = error

    @property
    def name(self) -> str:
        return self._name

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        if self._error:
            raise self._error
        return self._findings


def _make_finding(
    rule_id: str = "X-001",
    severity: Severity = Severity.HIGH,
    category: Category = Category.DEPENDENCY,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        category=category,
        severity=severity,
        message=f"Finding {rule_id}",
        location=Location(file="test.py", line=1),
    )


# ── ScanResult Tests ────────────────────────────────────────


class TestScanResultEdgeCases:
    def test_findings_above_info(self):
        """INFO threshold should return ALL findings."""
        findings = [
            _make_finding(severity=Severity.INFO),
            _make_finding(severity=Severity.LOW),
            _make_finding(severity=Severity.MEDIUM),
            _make_finding(severity=Severity.HIGH),
            _make_finding(severity=Severity.CRITICAL),
        ]
        result = ScanResult(findings=findings)
        assert len(result.findings_above(Severity.INFO)) == 5

    def test_findings_above_critical_only(self):
        """CRITICAL threshold should return only CRITICAL findings."""
        findings = [
            _make_finding(severity=Severity.HIGH),
            _make_finding(severity=Severity.MEDIUM),
        ]
        result = ScanResult(findings=findings)
        assert len(result.findings_above(Severity.CRITICAL)) == 0

    def test_medium_and_low_counts(self):
        findings = [
            _make_finding(severity=Severity.MEDIUM),
            _make_finding(severity=Severity.MEDIUM),
            _make_finding(severity=Severity.LOW),
        ]
        result = ScanResult(findings=findings)
        assert result.medium_count == 2
        assert result.low_count == 1

    def test_is_blocking_info_not_blocking(self):
        """INFO findings are not blocking."""
        f = _make_finding(severity=Severity.INFO)
        assert f.is_blocking is False

    def test_result_with_only_errors(self):
        result = ScanResult(errors=["Analyzer X failed"])
        assert result.findings == []
        assert result.has_blocking_findings is False
        assert len(result.errors) == 1


class TestSeveritySortOrder:
    def test_all_severities_in_sort_order(self):
        """Todas las severidades deben tener un orden de sort definido."""
        for sev in Severity:
            assert sev in SEVERITY_SORT_ORDER, (
                f"Severity {sev} missing from SEVERITY_SORT_ORDER"
            )

    def test_sort_order_correct(self):
        """CRITICAL < HIGH < MEDIUM < LOW < INFO en el sort order."""
        assert SEVERITY_SORT_ORDER[Severity.CRITICAL] < SEVERITY_SORT_ORDER[Severity.HIGH]
        assert SEVERITY_SORT_ORDER[Severity.HIGH] < SEVERITY_SORT_ORDER[Severity.MEDIUM]
        assert SEVERITY_SORT_ORDER[Severity.MEDIUM] < SEVERITY_SORT_ORDER[Severity.LOW]
        assert SEVERITY_SORT_ORDER[Severity.LOW] < SEVERITY_SORT_ORDER[Severity.INFO]


# ── ScanEngine Tests ────────────────────────────────────────


class TestScanEngineEdgeCases:
    def test_empty_project(self, tmp_path, default_config):
        """Un directorio vacio no crashea."""
        engine = ScanEngine(default_config)
        result = engine.run([str(tmp_path)])
        assert result.files_scanned == 0
        assert result.findings == []
        assert result.duration_seconds >= 0

    def test_multiple_analyzers_all_run(self, tmp_path, default_config):
        (tmp_path / "app.py").write_text("x = 1")
        a1 = FakeAnalyzer("analyzer-1", findings=[_make_finding("A-001")])
        a2 = FakeAnalyzer("analyzer-2", findings=[_make_finding("B-001")])
        engine = ScanEngine(default_config)
        engine.register_analyzer(a1)
        engine.register_analyzer(a2)
        result = engine.run([str(tmp_path)])
        assert len(result.findings) == 2
        assert set(result.analyzers_run) == {"analyzer-1", "analyzer-2"}

    def test_one_analyzer_fails_others_continue(self, tmp_path, default_config):
        """Si un analyzer falla, los demas siguen ejecutandose."""
        (tmp_path / "app.py").write_text("x = 1")
        broken = FakeAnalyzer("broken", error=RuntimeError("crash"))
        good = FakeAnalyzer("good", findings=[_make_finding("G-001")])
        engine = ScanEngine(default_config)
        engine.register_analyzer(broken)
        engine.register_analyzer(good)
        result = engine.run([str(tmp_path)])
        assert "good" in result.analyzers_run
        assert "broken" not in result.analyzers_run
        assert len(result.errors) == 1
        assert len(result.findings) == 1

    def test_rule_override_disable_and_severity_combined(self, tmp_path):
        """Disable y severity override en diferentes reglas."""
        config = ScanConfig(
            rules={
                "A-001": RuleOverride(enabled=False),
                "B-001": RuleOverride(severity="low"),
            }
        )
        (tmp_path / "app.py").write_text("x = 1")
        findings = [
            _make_finding("A-001", Severity.CRITICAL),
            _make_finding("B-001", Severity.CRITICAL),
            _make_finding("C-001", Severity.HIGH),
        ]
        analyzer = FakeAnalyzer("test", findings=findings)
        engine = ScanEngine(config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        # A-001 should be removed
        assert not any(f.rule_id == "A-001" for f in result.findings)
        # B-001 should have severity changed to LOW
        b_findings = [f for f in result.findings if f.rule_id == "B-001"]
        assert len(b_findings) == 1
        assert b_findings[0].severity == Severity.LOW
        # C-001 should be unchanged
        c_findings = [f for f in result.findings if f.rule_id == "C-001"]
        assert len(c_findings) == 1
        assert c_findings[0].severity == Severity.HIGH

    def test_exclude_rules_multiple(self, tmp_path):
        config = ScanConfig(exclude_rules=["A-001", "B-001"])
        (tmp_path / "app.py").write_text("x = 1")
        findings = [
            _make_finding("A-001"),
            _make_finding("B-001"),
            _make_finding("C-001"),
        ]
        analyzer = FakeAnalyzer("test", findings=findings)
        engine = ScanEngine(config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "C-001"

    def test_category_filter_multiple(self, tmp_path):
        """Filtrar por multiples categorias."""
        config = ScanConfig(categories=["auth", "secrets"])
        (tmp_path / "app.py").write_text("x = 1")

        dep_analyzer = FakeAnalyzer(
            "dep", Category.DEPENDENCY, [_make_finding("D-001", category=Category.DEPENDENCY)]
        )
        auth_analyzer = FakeAnalyzer(
            "auth", Category.AUTH, [_make_finding("A-001", category=Category.AUTH)]
        )
        sec_analyzer = FakeAnalyzer(
            "sec", Category.SECRETS, [_make_finding("S-001", category=Category.SECRETS)]
        )

        engine = ScanEngine(config)
        engine.register_analyzer(dep_analyzer)
        engine.register_analyzer(auth_analyzer)
        engine.register_analyzer(sec_analyzer)
        result = engine.run([str(tmp_path)])

        assert "dep" not in result.analyzers_run
        assert "auth" in result.analyzers_run
        assert "sec" in result.analyzers_run

    def test_nonexistent_scan_path(self, default_config):
        """Escanear un path que no existe no crashea."""
        engine = ScanEngine(default_config)
        result = engine.run(["/nonexistent/path/xyz"])
        assert result.files_scanned == 0

    def test_findings_stable_sort_within_severity(self, tmp_path, default_config):
        """Findings del mismo severity mantienen orden relativo (sort estable)."""
        (tmp_path / "app.py").write_text("x = 1")
        findings = [
            _make_finding("FIRST", Severity.HIGH),
            _make_finding("SECOND", Severity.HIGH),
            _make_finding("THIRD", Severity.HIGH),
        ]
        analyzer = FakeAnalyzer("test", findings=findings)
        engine = ScanEngine(default_config)
        engine.register_analyzer(analyzer)
        result = engine.run([str(tmp_path)])

        ids = [f.rule_id for f in result.findings]
        assert ids == ["FIRST", "SECOND", "THIRD"]

    def test_analyzer_exception_types(self, tmp_path, default_config):
        """Diferentes tipos de excepciones se capturan correctamente."""
        (tmp_path / "app.py").write_text("x = 1")

        for exc in [ValueError("bad"), TypeError("type"), KeyError("key")]:
            analyzer = FakeAnalyzer("err", error=exc)
            engine = ScanEngine(default_config)
            engine.register_analyzer(analyzer)
            result = engine.run([str(tmp_path)])
            assert len(result.errors) == 1

    def test_duration_positive(self, tmp_path, default_config):
        (tmp_path / "app.py").write_text("x = 1")
        engine = ScanEngine(default_config)
        result = engine.run([str(tmp_path)])
        assert result.duration_seconds >= 0
