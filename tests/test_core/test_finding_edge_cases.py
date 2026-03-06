"""Edge case tests para Finding, Severity, Category."""

import pytest

from vigil.core.finding import Category, Finding, Location, Severity


class TestSeverityEdgeCases:
    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError):
            Severity("invalid")

    def test_severity_is_string(self):
        """Severity hereda de str, se puede comparar como string."""
        assert isinstance(Severity.CRITICAL, str)
        assert Severity.HIGH == "high"
        assert Severity.HIGH.value == "high"

    @pytest.mark.parametrize("value", ["critical", "high", "medium", "low", "info"])
    def test_all_severity_values_constructible(self, value):
        sev = Severity(value)
        assert sev.value == value

    def test_severity_comparison(self):
        """Severities se pueden comparar como strings."""
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH != Severity.CRITICAL


class TestCategoryEdgeCases:
    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            Category("nonexistent")

    def test_category_is_string(self):
        assert isinstance(Category.DEPENDENCY, str)

    def test_test_quality_has_hyphen(self):
        """test-quality tiene un guion, no un underscore."""
        assert Category.TEST_QUALITY == "test-quality"
        assert Category.TEST_QUALITY.value == "test-quality"


class TestLocationEdgeCases:
    def test_location_line_zero(self):
        """Linea 0 es valida (algunas herramientas usan 0-indexed)."""
        loc = Location(file="test.py", line=0)
        assert loc.line == 0

    def test_location_empty_file(self):
        """Archivo vacio como nombre."""
        loc = Location(file="")
        assert loc.file == ""

    def test_location_with_path_separators(self):
        loc = Location(file="src/app/models/user.py", line=42)
        assert "/" in loc.file


class TestFindingEdgeCases:
    def test_finding_with_empty_message(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.LOW,
            message="",
            location=Location(file="x"),
        )
        assert f.message == ""

    def test_finding_with_unicode_message(self):
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.LOW,
            message="Paquete 'test' no existe en el registro publico",
            location=Location(file="x"),
        )
        assert "publico" in f.message

    def test_finding_metadata_mutable(self):
        """Metadata es un dict mutable."""
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.LOW,
            message="test",
            location=Location(file="x"),
        )
        f.metadata["key"] = "value"
        assert f.metadata["key"] == "value"

    def test_finding_severity_mutable(self):
        """Severity se puede cambiar (para overrides)."""
        f = Finding(
            rule_id="X-001",
            category=Category.DEPENDENCY,
            severity=Severity.CRITICAL,
            message="test",
            location=Location(file="x"),
        )
        assert f.is_blocking is True
        f.severity = Severity.LOW
        assert f.is_blocking is False

    def test_finding_metadata_default_not_shared(self):
        """Cada Finding tiene su propio dict de metadata."""
        f1 = Finding(
            rule_id="X-001", category=Category.DEPENDENCY,
            severity=Severity.LOW, message="t1", location=Location(file="x"),
        )
        f2 = Finding(
            rule_id="X-002", category=Category.DEPENDENCY,
            severity=Severity.LOW, message="t2", location=Location(file="x"),
        )
        f1.metadata["key"] = "f1_value"
        assert "key" not in f2.metadata, (
            "Metadata dict shared between Finding instances"
        )

    @pytest.mark.parametrize("severity,expected", [
        (Severity.CRITICAL, True),
        (Severity.HIGH, True),
        (Severity.MEDIUM, False),
        (Severity.LOW, False),
        (Severity.INFO, False),
    ])
    def test_is_blocking_all_severities(self, severity, expected):
        f = Finding(
            rule_id="X-001", category=Category.DEPENDENCY,
            severity=severity, message="test",
            location=Location(file="x"),
        )
        assert f.is_blocking is expected, (
            f"Severity {severity} should have is_blocking={expected}"
        )
