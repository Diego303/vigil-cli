"""Edge case tests para config schema."""

import pytest
from pydantic import ValidationError

from vigil.config.schema import (
    DepsConfig,
    OutputConfig,
    RuleOverride,
    ScanConfig,
    SecretsConfig,
)


class TestScanConfigValidation:
    def test_fail_on_rejects_invalid_value(self):
        """fail_on solo acepta valores de Severity validos."""
        with pytest.raises(ValidationError):
            ScanConfig(fail_on="banana")

    def test_fail_on_accepts_valid_values(self):
        for value in ["critical", "high", "medium", "low", "info"]:
            config = ScanConfig(fail_on=value)
            assert config.fail_on == value

    def test_empty_exclude_list(self):
        config = ScanConfig(exclude=[])
        assert config.exclude == []

    def test_empty_languages_list(self):
        config = ScanConfig(languages=[])
        assert config.languages == []

    def test_config_from_dict(self):
        """Config creada desde un dict (como viene de YAML)."""
        data = {
            "fail_on": "critical",
            "languages": ["python"],
            "deps": {"min_age_days": 60},
        }
        config = ScanConfig(**data)
        assert config.fail_on == "critical"
        assert config.deps.min_age_days == 60

    def test_nested_config_partial_override(self):
        """Solo parte de una config nested se sobreescribe."""
        config = ScanConfig(deps={"min_age_days": 90})
        assert config.deps.min_age_days == 90
        # Los demas campos deben tener defaults
        assert config.deps.verify_registry is True
        assert config.deps.cache_ttl_hours == 24

    def test_rule_override_invalid_severity(self):
        """Severity invalida en RuleOverride no se valida."""
        override = RuleOverride(severity="invalid_severity")
        assert override.severity == "invalid_severity"
        # Esto es un string libre — cuando se usa en engine, Severity("invalid")
        # lanzara ValueError

    def test_scan_config_immutability_of_defaults(self):
        """Cada instancia tiene sus propias listas de defaults."""
        config1 = ScanConfig()
        config2 = ScanConfig()
        config1.exclude.append("custom/")
        assert "custom/" not in config2.exclude, (
            "Default list mutation leaked between instances"
        )


class TestDepsConfigEdgeCases:
    def test_negative_min_age_days(self):
        """Pydantic permite valores negativos sin validacion custom."""
        config = DepsConfig(min_age_days=-1)
        assert config.min_age_days == -1

    def test_zero_similarity_threshold(self):
        config = DepsConfig(similarity_threshold=0.0)
        assert config.similarity_threshold == 0.0

    def test_high_similarity_threshold(self):
        config = DepsConfig(similarity_threshold=1.0)
        assert config.similarity_threshold == 1.0


class TestSecretsConfigEdgeCases:
    def test_default_placeholder_patterns_not_empty(self):
        config = SecretsConfig()
        assert len(config.placeholder_patterns) > 5

    def test_custom_placeholder_patterns(self):
        config = SecretsConfig(placeholder_patterns=["custom_pattern"])
        assert config.placeholder_patterns == ["custom_pattern"]

    def test_placeholder_patterns_default_independence(self):
        """Cada instancia tiene su propia lista de patterns."""
        c1 = SecretsConfig()
        c2 = SecretsConfig()
        c1.placeholder_patterns.append("extra")
        assert "extra" not in c2.placeholder_patterns


class TestOutputConfigEdgeCases:
    def test_all_supported_formats(self):
        """Todos los formatos soportados se aceptan."""
        for fmt in ["human", "json", "junit", "sarif"]:
            config = OutputConfig(format=fmt)
            assert config.format == fmt
