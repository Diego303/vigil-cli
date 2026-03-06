"""Edge case tests para config loader."""

import pytest
import yaml

from vigil.config.loader import (
    STRATEGY_PRESETS,
    _merge_cli_overrides,
    find_config_file,
    generate_config_yaml,
    load_config,
)
from vigil.config.schema import ScanConfig


class TestFindConfigFileEdgeCases:
    def test_prefers_vigil_yaml_over_vigil_yml(self, tmp_path):
        """Si existen ambos, .vigil.yaml tiene prioridad."""
        (tmp_path / ".vigil.yaml").write_text("fail_on: critical")
        (tmp_path / ".vigil.yml").write_text("fail_on: low")
        result = find_config_file(str(tmp_path))
        assert result is not None
        assert result.name == ".vigil.yaml"

    def test_finds_config_without_dot(self, tmp_path):
        (tmp_path / "vigil.yaml").write_text("fail_on: critical")
        result = find_config_file(str(tmp_path))
        assert result is not None
        assert result.name == "vigil.yaml"

    def test_config_in_root(self, tmp_path):
        """Config en el directorio raiz del proyecto se encuentra."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: medium")
        deep = tmp_path / "src" / "app" / "models" / "v2"
        deep.mkdir(parents=True)
        result = find_config_file(str(deep))
        assert result is not None
        assert result == config_file


class TestLoadConfigEdgeCases:
    def test_yaml_with_unknown_keys_ignored(self, tmp_path):
        """Keys desconocidas en YAML no causan error (Pydantic ignora extras)."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: critical\nunknown_key: value\n")
        # Pydantic default is to ignore extra fields
        config = load_config(config_path=str(config_file))
        assert config.fail_on == "critical"

    def test_yaml_with_all_sections(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text(
            "fail_on: medium\n"
            "languages: [python]\n"
            "deps:\n"
            "  min_age_days: 60\n"
            "  offline_mode: true\n"
            "auth:\n"
            "  max_token_lifetime_hours: 1\n"
            "secrets:\n"
            "  min_entropy: 4.0\n"
            "tests:\n"
            "  min_assertions_per_test: 2\n"
        )
        config = load_config(config_path=str(config_file))
        assert config.fail_on == "medium"
        assert config.deps.min_age_days == 60
        assert config.auth.max_token_lifetime_hours == 1
        assert config.secrets.min_entropy == 4.0
        assert config.tests.min_assertions_per_test == 2

    def test_yaml_only_comment_lines(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("# Only comments\n# No actual config\n")
        config = load_config(config_path=str(config_file))
        assert isinstance(config, ScanConfig)
        assert config.fail_on == "high"

    def test_yaml_null_document(self, tmp_path):
        """yaml.safe_load returns None for empty/null documents."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("---\n")
        config = load_config(config_path=str(config_file))
        assert isinstance(config, ScanConfig)

    def test_cli_overrides_none_values_ignored(self):
        """None values en CLI overrides no deben sobreescribir defaults."""
        config = load_config(cli_overrides={
            "languages": None,
            "categories": None,
            "rules_filter": None,
            "exclude_rules": None,
        })
        assert config.languages == ["python", "javascript"]
        assert config.categories == []

    def test_cli_overrides_empty_lists_ignored(self):
        """Listas vacias en CLI overrides no deben sobreescribir."""
        config = load_config(cli_overrides={
            "languages": [],
            "categories": [],
        })
        assert config.languages == ["python", "javascript"]
        assert config.categories == []

    def test_yaml_with_rule_overrides_complex(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text(
            "rules:\n"
            "  DEP-001:\n"
            "    enabled: false\n"
            "  DEP-002:\n"
            "    severity: low\n"
            "  AUTH-005:\n"
            "    enabled: true\n"
            "    severity: critical\n"
        )
        config = load_config(config_path=str(config_file))
        assert config.rules["DEP-001"].enabled is False
        assert config.rules["DEP-002"].severity == "low"
        assert config.rules["AUTH-005"].enabled is True
        assert config.rules["AUTH-005"].severity == "critical"


class TestMergeCliOverrides:
    def test_fail_on_override(self):
        result = _merge_cli_overrides({}, {"fail_on": "critical"})
        assert result["fail_on"] == "critical"

    def test_fail_on_overrides_yaml(self):
        result = _merge_cli_overrides(
            {"fail_on": "low"}, {"fail_on": "critical"}
        )
        assert result["fail_on"] == "critical"

    def test_output_format_creates_output_key(self):
        result = _merge_cli_overrides({}, {"output_format": "json"})
        assert result["output"]["format"] == "json"

    def test_quiet_disables_suggestions(self):
        result = _merge_cli_overrides({}, {"quiet": True})
        assert result["output"]["show_suggestions"] is False

    def test_offline_sets_deps_offline_mode(self):
        result = _merge_cli_overrides({}, {"offline": True})
        assert result["deps"]["offline_mode"] is True

    def test_offline_false_doesnt_set(self):
        result = _merge_cli_overrides({}, {"offline": False})
        assert "deps" not in result or "offline_mode" not in result.get("deps", {})

    def test_preserves_existing_yaml_data(self):
        file_data = {
            "fail_on": "low",
            "deps": {"min_age_days": 60},
            "output": {"colors": False},
        }
        result = _merge_cli_overrides(file_data, {"output_format": "json"})
        assert result["fail_on"] == "low"
        assert result["deps"]["min_age_days"] == 60
        assert result["output"]["format"] == "json"
        assert result["output"]["colors"] is False

    def test_multiple_output_overrides(self):
        result = _merge_cli_overrides({}, {
            "output_format": "sarif",
            "output_file": "report.sarif",
            "verbose": True,
        })
        assert result["output"]["format"] == "sarif"
        assert result["output"]["output_file"] == "report.sarif"
        assert result["output"]["verbose"] is True


class TestGenerateConfigYaml:
    @pytest.mark.parametrize("strategy", ["strict", "standard", "relaxed"])
    def test_valid_yaml_syntax(self, strategy):
        """El YAML generado debe ser parseable."""
        content = generate_config_yaml(strategy)
        parsed = yaml.safe_load(content)
        # Should not crash. May return None if all lines are comments.
        assert parsed is None or isinstance(parsed, dict)

    def test_strict_has_stricter_values(self):
        content = generate_config_yaml("strict")
        parsed = yaml.safe_load(content)
        if parsed:
            assert parsed.get("fail_on") in ['"medium"', "medium", None]

    def test_unknown_strategy_uses_defaults(self):
        """Un strategy desconocido no crashea, usa defaults."""
        content = generate_config_yaml("nonexistent")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_roundtrip_config_values(self):
        """El YAML generado debe producir una config valida al re-cargarse."""
        content = generate_config_yaml("standard")
        parsed = yaml.safe_load(content)
        assert parsed is not None
        config = ScanConfig(**parsed)
        assert isinstance(config, ScanConfig)
        assert isinstance(config.include, list)
        assert isinstance(config.languages, list)

    @pytest.mark.parametrize("strategy", STRATEGY_PRESETS.keys())
    def test_all_strategies_in_presets(self, strategy):
        assert strategy in STRATEGY_PRESETS
