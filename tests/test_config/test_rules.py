"""Tests para catalogo de reglas."""

from vigil.config.rules import RULES_V0, RuleDefinition
from vigil.core.finding import Category, Severity
from vigil.core.rule_registry import RuleRegistry


class TestRulesCatalog:
    def test_all_rules_have_required_fields(self):
        for rule in RULES_V0:
            assert rule.id, f"Rule missing id"
            assert rule.name, f"Rule {rule.id} missing name"
            assert rule.description, f"Rule {rule.id} missing description"
            assert isinstance(rule.category, Category), f"Rule {rule.id} invalid category"
            assert isinstance(rule.default_severity, Severity), f"Rule {rule.id} invalid severity"

    def test_rule_ids_unique(self):
        ids = [r.id for r in RULES_V0]
        assert len(ids) == len(set(ids)), "Duplicate rule IDs found"

    def test_rule_id_format(self):
        import re
        for rule in RULES_V0:
            assert re.match(r"^[A-Z]+-\d{3}$", rule.id), (
                f"Rule ID '{rule.id}' does not match format 'CAT-NNN'"
            )

    def test_all_categories_covered(self):
        categories = {r.category for r in RULES_V0}
        assert Category.DEPENDENCY in categories
        assert Category.AUTH in categories
        assert Category.SECRETS in categories
        assert Category.TEST_QUALITY in categories

    def test_dependency_rules_count(self):
        dep_rules = [r for r in RULES_V0 if r.category == Category.DEPENDENCY]
        assert len(dep_rules) == 7  # DEP-001 through DEP-007

    def test_auth_rules_count(self):
        auth_rules = [r for r in RULES_V0 if r.category == Category.AUTH]
        assert len(auth_rules) == 7  # AUTH-001 through AUTH-007

    def test_secrets_rules_count(self):
        sec_rules = [r for r in RULES_V0 if r.category == Category.SECRETS]
        assert len(sec_rules) == 6  # SEC-001 through SEC-006

    def test_test_quality_rules_count(self):
        test_rules = [r for r in RULES_V0 if r.category == Category.TEST_QUALITY]
        assert len(test_rules) == 6  # TEST-001 through TEST-006


class TestRuleRegistry:
    def test_loads_all_rules(self):
        registry = RuleRegistry()
        assert len(registry.all()) == len(RULES_V0)

    def test_get_existing_rule(self):
        registry = RuleRegistry()
        rule = registry.get("DEP-001")
        assert rule is not None
        assert rule.name == "Hallucinated dependency"
        assert rule.default_severity == Severity.CRITICAL

    def test_get_nonexistent_rule(self):
        registry = RuleRegistry()
        assert registry.get("FAKE-999") is None

    def test_by_category(self):
        registry = RuleRegistry()
        dep_rules = registry.by_category(Category.DEPENDENCY)
        assert all(r.category == Category.DEPENDENCY for r in dep_rules)
        assert len(dep_rules) > 0

    def test_by_severity(self):
        registry = RuleRegistry()
        critical = registry.by_severity(Severity.CRITICAL)
        assert all(r.default_severity == Severity.CRITICAL for r in critical)
        assert len(critical) > 0

    def test_enabled_rules_default(self):
        registry = RuleRegistry()
        enabled = registry.enabled_rules()
        assert len(enabled) == len(RULES_V0)  # All enabled by default

    def test_enabled_rules_with_override_disable(self):
        from vigil.config.schema import RuleOverride
        registry = RuleRegistry()
        overrides = {"DEP-001": RuleOverride(enabled=False)}
        enabled = registry.enabled_rules(overrides)
        assert not any(r.id == "DEP-001" for r in enabled)
        assert len(enabled) == len(RULES_V0) - 1
