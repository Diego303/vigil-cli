"""Tests para config loader."""

from vigil.config.loader import (
    find_config_file,
    generate_config_yaml,
    load_config,
)
from vigil.config.schema import ScanConfig


class TestFindConfigFile:
    def test_finds_vigil_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: critical")
        result = find_config_file(str(tmp_path))
        assert result is not None
        assert result.name == ".vigil.yaml"

    def test_finds_vigil_yml(self, tmp_path):
        config_file = tmp_path / ".vigil.yml"
        config_file.write_text("fail_on: critical")
        result = find_config_file(str(tmp_path))
        assert result is not None

    def test_no_config_file(self, tmp_path):
        subdir = tmp_path / "deep" / "nested"
        subdir.mkdir(parents=True)
        result = find_config_file(str(subdir))
        # May find one in a parent dir or return None
        # Depends on test environment
        # The important thing is it doesn't crash
        assert result is None or result.exists()

    def test_traverses_up(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: low")
        subdir = tmp_path / "src" / "app"
        subdir.mkdir(parents=True)
        result = find_config_file(str(subdir))
        assert result is not None
        assert result == config_file


class TestLoadConfig:
    def test_load_defaults(self):
        config = load_config()
        assert isinstance(config, ScanConfig)
        assert config.fail_on == "high"

    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: critical\nlanguages: [python]\n")
        config = load_config(config_path=str(config_file))
        assert config.fail_on == "critical"
        assert config.languages == ["python"]

    def test_load_with_nested_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text(
            "deps:\n  min_age_days: 60\n  offline_mode: true\n"
        )
        config = load_config(config_path=str(config_file))
        assert config.deps.min_age_days == 60
        assert config.deps.offline_mode is True

    def test_cli_overrides_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: low\n")
        config = load_config(
            config_path=str(config_file),
            cli_overrides={"fail_on": "critical"},
        )
        assert config.fail_on == "critical"

    def test_cli_offline_override(self):
        config = load_config(cli_overrides={"offline": True})
        assert config.deps.offline_mode is True

    def test_cli_output_format(self):
        config = load_config(cli_overrides={"output_format": "json"})
        assert config.output.format == "json"

    def test_cli_categories(self):
        config = load_config(
            cli_overrides={"categories": ["dependency", "auth"]}
        )
        assert config.categories == ["dependency", "auth"]

    def test_nonexistent_config_path(self):
        config = load_config(config_path="/nonexistent/.vigil.yaml")
        assert isinstance(config, ScanConfig)
        # Should fall back to defaults
        assert config.fail_on == "high"

    def test_invalid_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("{{invalid yaml::")
        config = load_config(config_path=str(config_file))
        # Should fall back to defaults on parse error
        assert isinstance(config, ScanConfig)

    def test_empty_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("")
        config = load_config(config_path=str(config_file))
        assert isinstance(config, ScanConfig)

    def test_rule_overrides_in_yaml(self, tmp_path):
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text(
            "rules:\n"
            "  DEP-001:\n"
            "    enabled: false\n"
            "  AUTH-003:\n"
            '    severity: "low"\n'
        )
        config = load_config(config_path=str(config_file))
        assert config.rules["DEP-001"].enabled is False
        assert config.rules["AUTH-003"].severity == "low"


class TestGenerateConfig:
    def test_standard_strategy(self):
        content = generate_config_yaml("standard")
        assert ".vigil.yaml" in content
        assert "standard" in content

    def test_strict_strategy(self):
        content = generate_config_yaml("strict")
        assert "strict" in content

    def test_relaxed_strategy(self):
        content = generate_config_yaml("relaxed")
        assert "relaxed" in content

    def test_content_is_valid_yaml(self):
        import yaml
        content = generate_config_yaml("standard")
        # Should parse without errors (comments lines with # are fine)
        parsed = yaml.safe_load(content)
        assert parsed is not None or content.strip().startswith("#")
