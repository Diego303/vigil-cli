"""Edge case tests para CLI."""

import json
import xml.etree.ElementTree as ET

import pytest
from click.testing import CliRunner

from vigil.cli import ExitCode, main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def clean_dir(tmp_path):
    """Directorio limpio sin fixtures problemáticas."""
    (tmp_path / "app.py").write_text("x = 1")
    return tmp_path


class TestScanCommand:
    def test_scan_default_path(self, runner, clean_dir):
        """scan con directorio limpio."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--offline"])
        assert result.exit_code == 0

    def test_scan_multiple_paths(self, runner, tmp_path):
        dir1 = tmp_path / "src"
        dir2 = tmp_path / "lib"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "app.py").write_text("x = 1")
        (dir2 / "util.py").write_text("y = 2")
        result = runner.invoke(main, ["scan", str(dir1), str(dir2), "--offline"])
        assert result.exit_code == 0

    def test_scan_json_output_is_valid(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--format", "json", "--offline"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data["findings"], list)
        assert isinstance(data["files_scanned"], int)
        assert isinstance(data["duration_seconds"], (int, float))

    def test_scan_sarif_output_valid_structure(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--format", "sarif", "--offline"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1
        assert "tool" in data["runs"][0]
        assert "results" in data["runs"][0]

    def test_scan_junit_output_valid_xml(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--format", "junit", "--offline"])
        assert result.exit_code == 0
        root = ET.fromstring(result.output)
        assert root.tag == "testsuites"
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("name") == "vigil"

    def test_scan_output_file_json(self, runner, clean_dir):
        output = clean_dir / "report.json"
        result = runner.invoke(
            main, ["scan", str(clean_dir), "--format", "json", "--output", str(output), "--offline"]
        )
        assert result.exit_code == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert "findings" in data

    def test_scan_output_file_nested_dir(self, runner, clean_dir):
        """--output con directorios inexistentes los crea automaticamente."""
        output = clean_dir / "reports" / "sub" / "report.json"
        result = runner.invoke(
            main, ["scan", str(clean_dir), "--format", "json", "--output", str(output), "--offline"]
        )
        assert result.exit_code == 0
        assert output.exists()

    def test_scan_output_file_sarif(self, runner, clean_dir):
        output = clean_dir / "report.sarif"
        result = runner.invoke(
            main, ["scan", str(clean_dir), "--format", "sarif", "--output", str(output), "--offline"]
        )
        assert result.exit_code == 0
        assert output.exists()

    def test_scan_offline_flag(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--offline"])
        assert result.exit_code == 0

    def test_scan_verbose_flag(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--verbose", "--offline"])
        assert result.exit_code == 0

    def test_scan_quiet_flag(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--quiet", "--offline"])
        assert result.exit_code == 0

    def test_scan_category_filter(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--category", "dependency", "--offline"])
        assert result.exit_code == 0

    def test_scan_multiple_categories(self, runner, clean_dir):
        result = runner.invoke(
            main, ["scan", str(clean_dir), "-C", "dependency", "-C", "auth", "--offline"]
        )
        assert result.exit_code == 0

    def test_scan_language_filter(self, runner, clean_dir):
        result = runner.invoke(main, ["scan", str(clean_dir), "--language", "python", "--offline"])
        assert result.exit_code == 0

    def test_scan_fail_on_critical(self, runner, clean_dir):
        """Con fail-on critical y sin findings, exit code 0."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--fail-on", "critical", "--offline"])
        assert result.exit_code == 0

    def test_scan_with_config_file(self, runner, clean_dir):
        config = clean_dir / "custom.yaml"
        config.write_text("fail_on: critical\nlanguages: [python]\n")
        result = runner.invoke(
            main, ["scan", str(clean_dir), "--config", str(config), "--offline"]
        )
        assert result.exit_code == 0

    def test_scan_with_nonexistent_config(self, runner, clean_dir):
        """Config file inexistente no crashea, usa defaults."""
        result = runner.invoke(
            main, ["scan", str(clean_dir), "--config", str(clean_dir / "nope.yaml"), "--offline"]
        )
        assert result.exit_code == 0

    def test_scan_invalid_format_rejected(self, runner):
        result = runner.invoke(main, ["scan", ".", "--format", "csv"])
        assert result.exit_code != 0


class TestDepsCommand:
    def test_deps_default(self, runner, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--offline"])
        assert result.exit_code == 0

    def test_deps_no_verify(self, runner, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--no-verify"])
        assert result.exit_code == 0

    def test_deps_json_format(self, runner, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--format", "json", "--offline"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "findings" in data

    def test_deps_offline(self, runner, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--offline"])
        assert result.exit_code == 0


class TestTestsCommand:
    def test_tests_default(self, runner, tmp_path):
        (tmp_path / "test_app.py").write_text("def test_x():\n    assert 1 + 1 == 2\n")
        result = runner.invoke(main, ["tests", str(tmp_path)])
        assert result.exit_code == 0

    def test_tests_min_assertions(self, runner, tmp_path):
        (tmp_path / "test_app.py").write_text("def test_x():\n    assert 1 + 1 == 2\n")
        result = runner.invoke(main, ["tests", str(tmp_path), "--min-assertions", "2"])
        # Only 1 assertion, min is 2 → findings → exit code 1
        assert result.exit_code == 1

    def test_tests_json_format(self, runner, tmp_path):
        (tmp_path / "test_app.py").write_text("def test_x():\n    assert 1 + 1 == 2\n")
        result = runner.invoke(main, ["tests", str(tmp_path), "--format", "json"])
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
        assert "1.0.0" in result.output
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
        result = runner.invoke(main, ["scan", str(tmp_path), "--offline"])
        assert result.exit_code == ExitCode.SUCCESS
