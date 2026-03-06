"""Edge case tests para CLI."""

import json
import xml.etree.ElementTree as ET

import pytest
from click.testing import CliRunner

from vigil.cli import ExitCode, main


@pytest.fixture
def runner():
    return CliRunner()


class TestScanCommand:
    def test_scan_default_path(self, runner):
        """scan sin argumentos escanea directorio actual."""
        result = runner.invoke(main, ["scan"])
        assert result.exit_code == 0

    def test_scan_multiple_paths(self, runner, tmp_path):
        dir1 = tmp_path / "src"
        dir2 = tmp_path / "lib"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "app.py").write_text("x = 1")
        (dir2 / "util.py").write_text("y = 2")
        result = runner.invoke(main, ["scan", str(dir1), str(dir2)])
        assert result.exit_code == 0

    def test_scan_json_output_is_valid(self, runner):
        result = runner.invoke(main, ["scan", ".", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data["findings"], list)
        assert isinstance(data["files_scanned"], int)
        assert isinstance(data["duration_seconds"], (int, float))

    def test_scan_sarif_output_valid_structure(self, runner):
        result = runner.invoke(main, ["scan", ".", "--format", "sarif"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1
        assert "tool" in data["runs"][0]
        assert "results" in data["runs"][0]

    def test_scan_junit_output_valid_xml(self, runner):
        result = runner.invoke(main, ["scan", ".", "--format", "junit"])
        assert result.exit_code == 0
        root = ET.fromstring(result.output)
        assert root.tag == "testsuites"
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("name") == "vigil"

    def test_scan_output_file_json(self, runner, tmp_path):
        output = tmp_path / "report.json"
        result = runner.invoke(
            main, ["scan", ".", "--format", "json", "--output", str(output)]
        )
        assert result.exit_code == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert "findings" in data

    def test_scan_output_file_nested_dir(self, runner, tmp_path):
        """--output con directorios inexistentes los crea automaticamente."""
        output = tmp_path / "reports" / "sub" / "report.json"
        result = runner.invoke(
            main, ["scan", ".", "--format", "json", "--output", str(output)]
        )
        assert result.exit_code == 0
        assert output.exists()

    def test_scan_output_file_sarif(self, runner, tmp_path):
        output = tmp_path / "report.sarif"
        result = runner.invoke(
            main, ["scan", ".", "--format", "sarif", "--output", str(output)]
        )
        assert result.exit_code == 0
        assert output.exists()

    def test_scan_offline_flag(self, runner):
        result = runner.invoke(main, ["scan", ".", "--offline"])
        assert result.exit_code == 0

    def test_scan_verbose_flag(self, runner):
        result = runner.invoke(main, ["scan", ".", "--verbose"])
        assert result.exit_code == 0

    def test_scan_quiet_flag(self, runner):
        result = runner.invoke(main, ["scan", ".", "--quiet"])
        assert result.exit_code == 0

    def test_scan_category_filter(self, runner):
        result = runner.invoke(main, ["scan", ".", "--category", "dependency"])
        assert result.exit_code == 0

    def test_scan_multiple_categories(self, runner):
        result = runner.invoke(
            main, ["scan", ".", "-C", "dependency", "-C", "auth"]
        )
        assert result.exit_code == 0

    def test_scan_language_filter(self, runner):
        result = runner.invoke(main, ["scan", ".", "--language", "python"])
        assert result.exit_code == 0

    def test_scan_fail_on_critical(self, runner):
        """Con fail-on critical y sin findings, exit code 0."""
        result = runner.invoke(main, ["scan", ".", "--fail-on", "critical"])
        assert result.exit_code == 0

    def test_scan_with_config_file(self, runner, tmp_path):
        config = tmp_path / "custom.yaml"
        config.write_text("fail_on: critical\nlanguages: [python]\n")
        result = runner.invoke(
            main, ["scan", ".", "--config", str(config)]
        )
        assert result.exit_code == 0

    def test_scan_with_nonexistent_config(self, runner, tmp_path):
        """Config file inexistente no crashea, usa defaults."""
        result = runner.invoke(
            main, ["scan", ".", "--config", str(tmp_path / "nope.yaml")]
        )
        assert result.exit_code == 0

    def test_scan_invalid_format_rejected(self, runner):
        result = runner.invoke(main, ["scan", ".", "--format", "csv"])
        assert result.exit_code != 0


class TestDepsCommand:
    def test_deps_default(self, runner):
        result = runner.invoke(main, ["deps"])
        assert result.exit_code == 0

    def test_deps_no_verify(self, runner):
        result = runner.invoke(main, ["deps", "--no-verify"])
        assert result.exit_code == 0

    def test_deps_json_format(self, runner):
        result = runner.invoke(main, ["deps", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "findings" in data

    def test_deps_offline(self, runner):
        result = runner.invoke(main, ["deps", "--offline"])
        assert result.exit_code == 0


class TestTestsCommand:
    def test_tests_default(self, runner):
        result = runner.invoke(main, ["tests"])
        assert result.exit_code == 0

    def test_tests_min_assertions(self, runner):
        result = runner.invoke(main, ["tests", "--min-assertions", "2"])
        assert result.exit_code == 0

    def test_tests_json_format(self, runner):
        result = runner.invoke(main, ["tests", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "findings" in data


class TestInitCommand:
    def test_init_creates_vigil_yaml(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        config_file = tmp_path / ".vigil.yaml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "vigil" in content.lower() or "fail_on" in content

    def test_init_refuses_overwrite(self, runner, tmp_path):
        (tmp_path / ".vigil.yaml").write_text("existing: true")
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == ExitCode.ERROR
        assert "already exists" in result.output

    def test_init_force_flag(self, runner, tmp_path):
        (tmp_path / ".vigil.yaml").write_text("existing: true")
        result = runner.invoke(main, ["init", "--force", str(tmp_path)])
        assert result.exit_code == 0
        content = (tmp_path / ".vigil.yaml").read_text()
        assert "existing" not in content

    @pytest.mark.parametrize("strategy", ["strict", "standard", "relaxed"])
    def test_init_strategies(self, runner, tmp_path, strategy):
        result = runner.invoke(
            main, ["init", "--strategy", strategy, str(tmp_path)]
        )
        assert result.exit_code == 0
        content = (tmp_path / ".vigil.yaml").read_text()
        assert strategy in content

    def test_init_nonexistent_directory(self, runner):
        result = runner.invoke(main, ["init", "/nonexistent/path"])
        assert result.exit_code == ExitCode.ERROR
        assert "does not exist" in result.output


class TestRulesCommand:
    def test_rules_lists_all_categories(self, runner):
        result = runner.invoke(main, ["rules"])
        assert result.exit_code == 0
        assert "DEPENDENCY" in result.output
        assert "AUTH" in result.output
        assert "SECRETS" in result.output
        assert "TEST-QUALITY" in result.output

    def test_rules_lists_specific_rules(self, runner):
        result = runner.invoke(main, ["rules"])
        assert result.exit_code == 0
        for rule_id in ["DEP-001", "AUTH-001", "SEC-001", "TEST-001"]:
            assert rule_id in result.output, f"Rule {rule_id} not in output"

    def test_rules_shows_severity(self, runner):
        result = runner.invoke(main, ["rules"])
        assert "CRITICAL" in result.output
        assert "HIGH" in result.output

    def test_rules_shows_owasp_refs(self, runner):
        result = runner.invoke(main, ["rules"])
        assert "OWASP" in result.output or "LLM03" in result.output


class TestVersionAndHelp:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
        assert "vigil" in result.output

    def test_help_shows_all_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in ["scan", "deps", "tests", "init", "rules"]:
            assert cmd in result.output

    def test_scan_help(self, runner):
        result = runner.invoke(main, ["scan", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--fail-on" in result.output
        assert "--category" in result.output
        assert "--rule" in result.output
        assert "--exclude-rule" in result.output
        assert "--language" in result.output
        assert "--offline" in result.output
        assert "--changed-only" in result.output
        assert "--verbose" in result.output
        assert "--quiet" in result.output

    def test_deps_help(self, runner):
        result = runner.invoke(main, ["deps", "--help"])
        assert result.exit_code == 0
        assert "--verify" in result.output

    def test_tests_help(self, runner):
        result = runner.invoke(main, ["tests", "--help"])
        assert result.exit_code == 0
        assert "--min-assertions" in result.output


class TestExitCodes:
    def test_exit_code_values(self):
        assert ExitCode.SUCCESS == 0
        assert ExitCode.FINDINGS == 1
        assert ExitCode.ERROR == 2

    def test_no_findings_returns_success(self, runner, tmp_path):
        """Sin findings, exit code es 0 (SUCCESS)."""
        (tmp_path / "clean.py").write_text("x = 1")
        result = runner.invoke(main, ["scan", str(tmp_path)])
        assert result.exit_code == ExitCode.SUCCESS
