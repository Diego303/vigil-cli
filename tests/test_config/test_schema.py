"""Tests para config schema (Pydantic models)."""

import pytest
from pydantic import ValidationError

from vigil.config.schema import (
    AuthConfig,
    DepsConfig,
    OutputConfig,
    RuleOverride,
    ScanConfig,
    SecretsConfig,
    TestQualityConfig,
)


class TestScanConfig:
    def test_defaults(self):
        config = ScanConfig()
        assert config.fail_on == "high"
        assert "python" in config.languages
        assert "javascript" in config.languages
        assert "node_modules/" in config.exclude
        assert ".venv/" in config.exclude

    def test_custom_values(self):
        config = ScanConfig(
            fail_on="critical",
            languages=["python"],
            exclude=["vendor/"],
        )
        assert config.fail_on == "critical"
        assert config.languages == ["python"]
        assert config.exclude == ["vendor/"]

    def test_nested_configs_defaults(self):
        config = ScanConfig()
        assert config.deps.verify_registry is True
        assert config.deps.min_age_days == 30
        assert config.auth.max_token_lifetime_hours == 24
        assert config.secrets.min_entropy == 3.0
        assert config.tests.min_assertions_per_test == 1

    def test_rule_overrides(self):
        config = ScanConfig(
            rules={
                "DEP-001": RuleOverride(enabled=False),
                "AUTH-003": RuleOverride(severity="low"),
            }
        )
        assert config.rules["DEP-001"].enabled is False
        assert config.rules["AUTH-003"].severity == "low"


class TestDepsConfig:
    def test_defaults(self):
        config = DepsConfig()
        assert config.verify_registry is True
        assert config.min_age_days == 30
        assert config.offline_mode is False
        assert config.cache_ttl_hours == 24

    def test_custom(self):
        config = DepsConfig(min_age_days=60, offline_mode=True)
        assert config.min_age_days == 60
        assert config.offline_mode is True


class TestAuthConfig:
    def test_defaults(self):
        config = AuthConfig()
        assert config.max_token_lifetime_hours == 24
        assert config.require_auth_on_mutating is True
        assert config.cors_allow_localhost is True


class TestSecretsConfig:
    def test_defaults(self):
        config = SecretsConfig()
        assert config.min_entropy == 3.0
        assert config.check_env_example is True
        assert len(config.placeholder_patterns) > 0
        assert "changeme" in config.placeholder_patterns


class TestTestQualityConfig:
    def test_defaults(self):
        config = TestQualityConfig()
        assert config.min_assertions_per_test == 1
        assert config.detect_trivial_asserts is True
        assert config.detect_mock_mirrors is True


class TestOutputConfig:
    def test_defaults(self):
        config = OutputConfig()
        assert config.format == "human"
        assert config.output_file is None
        assert config.colors is True
        assert config.verbose is False


class TestRuleOverride:
    def test_all_none(self):
        override = RuleOverride()
        assert override.enabled is None
        assert override.severity is None

    def test_disable(self):
        override = RuleOverride(enabled=False)
        assert override.enabled is False

    def test_severity_override(self):
        override = RuleOverride(severity="low")
        assert override.severity == "low"
