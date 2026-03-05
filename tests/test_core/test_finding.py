"""Tests para modelos de datos: Finding, Severity, Category, Location."""

from vigil.core.finding import Category, Finding, Location, Severity


class TestSeverity:
    def test_severity_values(self):
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"
        assert Severity.LOW == "low"
        assert Severity.INFO == "info"

    def test_severity_from_string(self):
        assert Severity("critical") is Severity.CRITICAL
        assert Severity("high") is Severity.HIGH

    def test_all_severities_exist(self):
        assert len(Severity) == 5


class TestCategory:
    def test_category_values(self):
        assert Category.DEPENDENCY == "dependency"
        assert Category.AUTH == "auth"
        assert Category.SECRETS == "secrets"
        assert Category.TEST_QUALITY == "test-quality"


class TestLocation:
    def test_minimal_location(self):
        loc = Location(file="foo.py")
        assert loc.file == "foo.py"
        assert loc.line is None
        assert loc.column is None
        assert loc.snippet is None

    def test_full_location(self):
        loc = Location(
            file="src/main.py",
            line=42,
            column=5,
            end_line=44,
            snippet="import os",
        )
        assert loc.file == "src/main.py"
        assert loc.line == 42
        assert loc.column == 5
        assert loc.end_line == 44
        assert loc.snippet == "import os"


class TestFinding:
    def test_finding_creation(self, sample_finding):
        assert sample_finding.rule_id == "DEP-001"
        assert sample_finding.category == Category.DEPENDENCY
        assert sample_finding.severity == Severity.CRITICAL
        assert "fake-pkg" in sample_finding.message
        assert sample_finding.location.file == "requirements.txt"
        assert sample_finding.suggestion is not None
        assert sample_finding.metadata["package"] == "fake-pkg"

    def test_is_blocking_critical(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.CRITICAL,
            message="test",
            location=Location(file="x"),
        )
        assert f.is_blocking is True

    def test_is_blocking_high(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.HIGH,
            message="test",
            location=Location(file="x"),
        )
        assert f.is_blocking is True

    def test_not_blocking_medium(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.MEDIUM,
            message="test",
            location=Location(file="x"),
        )
        assert f.is_blocking is False

    def test_not_blocking_low(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.LOW,
            message="test",
            location=Location(file="x"),
        )
        assert f.is_blocking is False

    def test_default_metadata_empty(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.LOW,
            message="test",
            location=Location(file="x"),
        )
        assert f.metadata == {}
