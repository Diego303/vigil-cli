"""Registry de reglas built-in con filtering."""

from vigil.config.rules import RULES_V0, RuleDefinition
from vigil.core.finding import Category, Severity


class RuleRegistry:
    """Registro central de reglas de vigil."""

    def __init__(self) -> None:
        self._rules: dict[str, RuleDefinition] = {}
        self._load_builtin_rules()

    def _load_builtin_rules(self) -> None:
        for rule in RULES_V0:
            self._rules[rule.id] = rule

    def get(self, rule_id: str) -> RuleDefinition | None:
        return self._rules.get(rule_id)

    def all(self) -> list[RuleDefinition]:
        return list(self._rules.values())

    def by_category(self, category: Category) -> list[RuleDefinition]:
        return [r for r in self._rules.values() if r.category == category]

    def by_severity(self, severity: Severity) -> list[RuleDefinition]:
        return [r for r in self._rules.values() if r.default_severity == severity]

    def enabled_rules(
        self,
        overrides: dict | None = None,
    ) -> list[RuleDefinition]:
        """Retorna reglas habilitadas, aplicando overrides."""
        overrides = overrides or {}
        enabled = []
        for rule in self._rules.values():
            override = overrides.get(rule.id)
            if override and override.enabled is False:
                continue
            if not rule.enabled_by_default:
                if not (override and override.enabled is True):
                    continue
            enabled.append(rule)
        return enabled
