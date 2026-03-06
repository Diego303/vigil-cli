"""Edge case tests para catalogo de reglas y RuleRegistry."""

import re

import pytest

from vigil.config.rules import RULES_V0, RuleDefinition
from vigil.config.schema import RuleOverride
from vigil.core.finding import Category, Severity
from vigil.core.rule_registry import RuleRegistry


class TestRulesCatalogIntegrity:
    """Verifica integridad y consistencia del catalogo de reglas."""

    def test_total_rules_count(self):
        """V0 debe tener exactamente 26 reglas."""
        assert len(RULES_V0) == 26

    def test_rule_id_prefixes_match_categories(self):
        """El prefijo del rule_id debe corresponder a la categoria."""
        prefix_map = {
            "DEP": Category.DEPENDENCY,
            "AUTH": Category.AUTH,
            "SEC": Category.SECRETS,
            "TEST": Category.TEST_QUALITY,
        }
        for rule in RULES_V0:
            prefix = rule.id.split("-")[0]
            expected_category = prefix_map.get(prefix)
            assert expected_category is not None, (
                f"Unknown prefix '{prefix}' in rule {rule.id}"
            )
            assert rule.category == expected_category, (
                f"Rule {rule.id} has category {rule.category} "
                f"but prefix '{prefix}' implies {expected_category}"
            )

    def test_rule_ids_sequential(self):
        """Los IDs de cada categoria deben ser secuenciales."""
        by_prefix: dict[str, list[int]] = {}
        for rule in RULES_V0:
            prefix, num = rule.id.split("-")
            by_prefix.setdefault(prefix, []).append(int(num))

        for prefix, nums in by_prefix.items():
            nums.sort()
            expected = list(range(1, len(nums) + 1))
            assert nums == expected, (
                f"Rule IDs for {prefix} are not sequential: {nums}"
            )

    def test_all_rules_enabled_by_default(self):
        """En V0, todas las reglas estan habilitadas por defecto."""
        for rule in RULES_V0:
            assert rule.enabled_by_default is True, (
                f"Rule {rule.id} is not enabled by default"
            )

    def test_rule_names_not_empty(self):
        for rule in RULES_V0:
            assert len(rule.name.strip()) > 0, f"Rule {rule.id} has empty name"

    def test_rule_descriptions_not_empty(self):
        for rule in RULES_V0:
            assert len(rule.description.strip()) > 0, (
                f"Rule {rule.id} has empty description"
            )

    def test_critical_rules_have_cwe(self):
        """Reglas CRITICAL deberian tener referencia CWE.
        Excepcion conocida: DEP-007 no tiene CWE asignado en el plan.
        """
        exceptions = {"DEP-007", "SEC-006"}  # No CWE in plan spec
        for rule in RULES_V0:
            if rule.default_severity == Severity.CRITICAL and rule.id not in exceptions:
                assert rule.cwe_ref is not None, (
                    f"Critical rule {rule.id} ({rule.name}) has no CWE reference"
                )

    def test_dependency_rules_severities(self):
        """Verificar severidades segun el plan."""
        severity_map = {
            "DEP-001": Severity.CRITICAL,
            "DEP-002": Severity.HIGH,
            "DEP-003": Severity.HIGH,
            "DEP-004": Severity.MEDIUM,
            "DEP-005": Severity.MEDIUM,
            "DEP-006": Severity.HIGH,
            "DEP-007": Severity.CRITICAL,
        }
        for rule_id, expected_sev in severity_map.items():
            rule = next(r for r in RULES_V0 if r.id == rule_id)
            assert rule.default_severity == expected_sev, (
                f"Rule {rule_id} has severity {rule.default_severity}, "
                f"expected {expected_sev}"
            )

    def test_auth_rules_severities(self):
        severity_map = {
            "AUTH-001": Severity.HIGH,
            "AUTH-002": Severity.HIGH,
            "AUTH-003": Severity.MEDIUM,
            "AUTH-004": Severity.CRITICAL,
            "AUTH-005": Severity.HIGH,
            "AUTH-006": Severity.MEDIUM,
            "AUTH-007": Severity.MEDIUM,
        }
        for rule_id, expected_sev in severity_map.items():
            rule = next(r for r in RULES_V0 if r.id == rule_id)
            assert rule.default_severity == expected_sev, (
                f"Rule {rule_id} has severity {rule.default_severity}, "
                f"expected {expected_sev}"
            )

    def test_secrets_rules_severities(self):
        severity_map = {
            "SEC-001": Severity.CRITICAL,
            "SEC-002": Severity.CRITICAL,
            "SEC-003": Severity.CRITICAL,
            "SEC-004": Severity.HIGH,
            "SEC-005": Severity.HIGH,
            "SEC-006": Severity.CRITICAL,
        }
        for rule_id, expected_sev in severity_map.items():
            rule = next(r for r in RULES_V0 if r.id == rule_id)
            assert rule.default_severity == expected_sev, (
                f"Rule {rule_id} has severity {rule.default_severity}, "
                f"expected {expected_sev}"
            )

    def test_test_quality_rules_severities(self):
        severity_map = {
            "TEST-001": Severity.HIGH,
            "TEST-002": Severity.MEDIUM,
            "TEST-003": Severity.MEDIUM,
            "TEST-004": Severity.LOW,
            "TEST-005": Severity.MEDIUM,
            "TEST-006": Severity.MEDIUM,
        }
        for rule_id, expected_sev in severity_map.items():
            rule = next(r for r in RULES_V0 if r.id == rule_id)
            assert rule.default_severity == expected_sev, (
                f"Rule {rule_id} has severity {rule.default_severity}, "
                f"expected {expected_sev}"
            )


class TestRuleDefinitionDataclass:
    def test_default_values(self):
        rule = RuleDefinition(
            id="X-001",
            name="Test",
            description="A test rule",
            category=Category.DEPENDENCY,
            default_severity=Severity.LOW,
        )
        assert rule.enabled_by_default is True
        assert rule.languages == []
        assert rule.owasp_ref is None
        assert rule.cwe_ref is None

    def test_with_all_fields(self):
        rule = RuleDefinition(
            id="X-001",
            name="Test",
            description="A test rule",
            category=Category.AUTH,
            default_severity=Severity.CRITICAL,
            enabled_by_default=False,
            languages=["python"],
            owasp_ref="LLM01",
            cwe_ref="CWE-123",
        )
        assert rule.enabled_by_default is False
        assert rule.languages == ["python"]
        assert rule.owasp_ref == "LLM01"
        assert rule.cwe_ref == "CWE-123"


class TestRuleRegistryEdgeCases:
    def test_by_category_empty(self):
        """Buscar por una categoria que no existe retorna lista vacia.
        En practica todas las categorias tienen reglas, pero probamos
        que no crashea.
        """
        registry = RuleRegistry()
        # Todas las categorias tienen reglas, pero vamos a verificar que la
        # funcion retorna una lista
        result = registry.by_category(Category.DEPENDENCY)
        assert isinstance(result, list)
        assert len(result) == 7

    def test_enabled_rules_with_enable_override(self):
        """Override enable=True en una regla ya habilitada no cambia nada."""
        registry = RuleRegistry()
        overrides = {"DEP-001": RuleOverride(enabled=True)}
        enabled = registry.enabled_rules(overrides)
        assert any(r.id == "DEP-001" for r in enabled)
        assert len(enabled) == len(RULES_V0)

    def test_enabled_rules_none_overrides(self):
        registry = RuleRegistry()
        enabled = registry.enabled_rules(None)
        assert len(enabled) == len(RULES_V0)

    def test_get_returns_correct_rule(self):
        registry = RuleRegistry()
        for rule in RULES_V0:
            fetched = registry.get(rule.id)
            assert fetched is not None
            assert fetched.id == rule.id
            assert fetched.name == rule.name

    def test_multiple_disables(self):
        registry = RuleRegistry()
        overrides = {
            "DEP-001": RuleOverride(enabled=False),
            "DEP-002": RuleOverride(enabled=False),
            "AUTH-001": RuleOverride(enabled=False),
        }
        enabled = registry.enabled_rules(overrides)
        disabled_ids = {"DEP-001", "DEP-002", "AUTH-001"}
        for rule in enabled:
            assert rule.id not in disabled_ids
        assert len(enabled) == len(RULES_V0) - 3
