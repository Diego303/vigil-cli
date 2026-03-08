"""Tests para la CLI de vigil."""

from click.testing import CliRunner

from vigil.cli import main


class TestCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_help(self):
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "vigil" in result.output
        assert "scan" in result.output
        assert "deps" in result.output
        assert "tests" in result.output
        assert "init" in result.output
        assert "rules" in result.output

    def test_version(self):
        result = self.runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.7.0" in result.output

    def test_scan_help(self):
        result = self.runner.invoke(main, ["scan", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--fail-on" in result.output
        assert "--offline" in result.output

    def test_scan_current_dir(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        result = self.runner.invoke(main, ["scan", str(tmp_path), "--offline"])
        assert result.exit_code == 0
        assert "findings" in result.output

    def test_scan_nonexistent_dir(self, tmp_path):
        """Scanning a nonexistent path within a clean dir produces no findings."""
        nonexistent = tmp_path / "nonexistent"
        result = self.runner.invoke(main, ["scan", str(nonexistent), "--offline"])
        assert result.exit_code == 0  # No findings = success
        assert "0 files" in result.output or "scanned" in result.output

    def test_scan_json_format(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        result = self.runner.invoke(main, ["scan", str(tmp_path), "--format", "json", "--offline"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "findings" in data

    def test_scan_sarif_format(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        result = self.runner.invoke(main, ["scan", str(tmp_path), "--format", "sarif", "--offline"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"

    def test_scan_junit_format(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        result = self.runner.invoke(main, ["scan", str(tmp_path), "--format", "junit", "--offline"])
        assert result.exit_code == 0
        assert "<?xml" in result.output

    def test_scan_with_output_file(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        output_file = tmp_path / "reports" / "report.json"
        result = self.runner.invoke(
            main,
            ["scan", str(tmp_path), "--format", "json", "--output", str(output_file), "--offline"],
        )
        assert result.exit_code == 0
        assert output_file.exists()
        import json
        data = json.loads(output_file.read_text())
        assert "findings" in data

    def test_deps_help(self):
        result = self.runner.invoke(main, ["deps", "--help"])
        assert result.exit_code == 0
        assert "--verify" in result.output

    def test_deps_command(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = self.runner.invoke(main, ["deps", str(tmp_path), "--offline"])
        assert result.exit_code == 0

    def test_tests_help(self):
        result = self.runner.invoke(main, ["tests", "--help"])
        assert result.exit_code == 0
        assert "--min-assertions" in result.output

    def test_rules_command(self):
        result = self.runner.invoke(main, ["rules"])
        assert result.exit_code == 0
        assert "DEP-001" in result.output
        assert "AUTH-001" in result.output
        assert "SEC-001" in result.output
        assert "TEST-001" in result.output

    def test_init_creates_config(self, tmp_path):
        result = self.runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".vigil.yaml").exists()

    def test_init_doesnt_overwrite(self, tmp_path):
        (tmp_path / ".vigil.yaml").write_text("existing: true")
        result = self.runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 2
        assert "already exists" in result.output

    def test_init_force_overwrites(self, tmp_path):
        (tmp_path / ".vigil.yaml").write_text("existing: true")
        result = self.runner.invoke(
            main, ["init", "--force", str(tmp_path)]
        )
        assert result.exit_code == 0

    def test_init_strict_strategy(self, tmp_path):
        result = self.runner.invoke(
            main, ["init", "--strategy", "strict", str(tmp_path)]
        )
        assert result.exit_code == 0
        content = (tmp_path / ".vigil.yaml").read_text()
        assert "strict" in content

    def test_init_nonexistent_dir(self):
        result = self.runner.invoke(main, ["init", "/nonexistent/dir"])
        assert result.exit_code == 2

    def test_scan_with_config(self, tmp_path):
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("fail_on: critical\n")
        (tmp_path / "test.py").write_text("x = 1")
        result = self.runner.invoke(
            main,
            ["scan", str(tmp_path), "--config", str(config_file), "--offline"],
        )
        assert result.exit_code == 0
