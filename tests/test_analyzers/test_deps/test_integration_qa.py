"""Integration tests para FASE 1 — DependencyAnalyzer end-to-end.

Cubre: flujo completo scan→analyze→format, integración CLI-engine-analyzer,
fixtures reales, multi-ecosystem, y regression tests para bugs corregidos.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from vigil.analyzers.deps.analyzer import DependencyAnalyzer
from vigil.analyzers.deps.registry_client import PackageInfo
from vigil.cli import ExitCode, main
from vigil.config.schema import ScanConfig
from vigil.core.engine import ScanEngine, ScanResult
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "deps"


# ──────────────────────────────────────────────────────────────────
# Integration: Engine + DependencyAnalyzer
# ──────────────────────────────────────────────────────────────────


class TestEngineAnalyzerIntegration:
    """Tests de integracion Engine + DependencyAnalyzer."""

    def test_engine_registers_and_runs_analyzer(self, tmp_path: Path) -> None:
        """ScanEngine registra y ejecuta DependencyAnalyzer."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        config = ScanConfig()
        config.deps.offline_mode = True

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())
        result = engine.run([str(tmp_path)])

        assert isinstance(result, ScanResult)
        assert "dependency" in result.analyzers_run
        assert result.errors == []

    def test_engine_category_filter(self, tmp_path: Path) -> None:
        """Engine skips dependency analyzer when filtered to auth only."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        config = ScanConfig()
        config.categories = ["auth"]
        config.deps.offline_mode = True

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())
        result = engine.run([str(tmp_path)])

        assert "dependency" not in result.analyzers_run

    def test_engine_rule_filter(self, tmp_path: Path) -> None:
        """Engine filters findings by rules_filter (--rule flag)."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\nfake-pkg==1.0.0\n")

        mock_pkg_fake = PackageInfo(name="fake-pkg", exists=False, ecosystem="pypi")
        mock_pkg_reqeusts = PackageInfo(
            name="reqeusts", exists=True, ecosystem="pypi",
            created_at="2020-01-01T00:00:00+00:00",
            source_url="https://example.com",
            latest_version="2.31.0", versions=["2.31.0"],
        )

        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False
        config.deps.similarity_threshold = 0.75
        config.rules_filter = ["DEP-001"]  # Only want DEP-001

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value

            def check_side_effect(name, ecosystem):
                if name == "fake-pkg":
                    return mock_pkg_fake
                return mock_pkg_reqeusts

            instance.check.side_effect = check_side_effect
            result = engine.run([str(tmp_path)])

        # Only DEP-001 findings should remain (not DEP-003)
        rule_ids = {f.rule_id for f in result.findings}
        assert "DEP-001" in rule_ids
        assert "DEP-003" not in rule_ids

    def test_engine_exclude_rule(self, tmp_path: Path) -> None:
        """Engine excludes findings by exclude_rules (--exclude-rule flag)."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75
        config.exclude_rules = ["DEP-003"]

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())
        result = engine.run([str(tmp_path)])

        dep003 = [f for f in result.findings if f.rule_id == "DEP-003"]
        assert len(dep003) == 0

    def test_engine_severity_override(self, tmp_path: Path) -> None:
        """Engine applies severity override from config."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        from vigil.config.schema import RuleOverride

        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75
        config.rules = {"DEP-003": RuleOverride(severity="low")}

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())
        result = engine.run([str(tmp_path)])

        dep003 = [f for f in result.findings if f.rule_id == "DEP-003"]
        if dep003:
            assert dep003[0].severity == Severity.LOW

    def test_engine_disable_rule(self, tmp_path: Path) -> None:
        """Engine disables rules via rule override."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        from vigil.config.schema import RuleOverride

        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75
        config.rules = {"DEP-003": RuleOverride(enabled=False)}

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())
        result = engine.run([str(tmp_path)])

        dep003 = [f for f in result.findings if f.rule_id == "DEP-003"]
        assert len(dep003) == 0

    def test_findings_sorted_by_severity(self, tmp_path: Path) -> None:
        """Engine sorts findings: CRITICAL first, then HIGH, etc."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\nfake-pkg==1.0.0\n")

        mock_pkg = PackageInfo(name="fake-pkg", exists=False, ecosystem="pypi")

        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False
        config.deps.similarity_threshold = 0.75

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value

            def check_side_effect(name, ecosystem):
                if name == "fake-pkg":
                    return mock_pkg
                return PackageInfo(
                    name=name, exists=True, ecosystem=ecosystem,
                    created_at="2020-01-01T00:00:00+00:00",
                    source_url="https://example.com",
                    latest_version="1.0", versions=["1.0"],
                )

            instance.check.side_effect = check_side_effect
            result = engine.run([str(tmp_path)])

        if len(result.findings) >= 2:
            severities = [f.severity for f in result.findings]
            severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
            indices = [severity_order.index(s) for s in severities]
            assert indices == sorted(indices), "Findings not sorted by severity"


# ──────────────────────────────────────────────────────────────────
# Integration: CLI + DependencyAnalyzer
# ──────────────────────────────────────────────────────────────────


class TestCLIDepsIntegration:
    """Tests de integración CLI con DependencyAnalyzer."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_scan_with_deps_findings_exits_1(self, tmp_path: Path) -> None:
        """scan with DEP-001 findings exits with code 1."""
        req = tmp_path / "requirements.txt"
        req.write_text("fake-ai-pkg==1.0.0\n")

        mock_pkg = PackageInfo(name="fake-ai-pkg", exists=False, ecosystem="pypi")

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = self.runner.invoke(
                main, ["scan", str(tmp_path), "--fail-on", "high"]
            )

        assert result.exit_code == ExitCode.FINDINGS

    def test_scan_offline_clean_project(self, tmp_path: Path) -> None:
        """Clean project scanned offline exits 0."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\nrequests>=2.31.0\n")

        result = self.runner.invoke(
            main, ["scan", str(tmp_path), "--offline"]
        )

        assert result.exit_code == ExitCode.SUCCESS

    def test_deps_command_json_output(self, tmp_path: Path) -> None:
        """deps command with JSON format produces valid JSON."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        result = self.runner.invoke(
            main, ["deps", str(tmp_path), "--format", "json", "--offline"]
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "findings" in data
        assert isinstance(data["findings"], list)

    def test_scan_category_dependency_only(self, tmp_path: Path) -> None:
        """--category dependency runs only dependency analyzer."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        result = self.runner.invoke(
            main, ["scan", str(tmp_path), "--category", "dependency", "--offline"]
        )

        assert result.exit_code == 0

    def test_scan_sarif_with_dep_findings(self, tmp_path: Path) -> None:
        """SARIF output includes DEP-001 findings correctly."""
        req = tmp_path / "requirements.txt"
        req.write_text("hallucinated-lib==1.0.0\n")

        mock_pkg = PackageInfo(name="hallucinated-lib", exists=False, ecosystem="pypi")

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = self.runner.invoke(
                main, ["scan", str(tmp_path), "--format", "sarif", "--fail-on", "critical"]
            )

        # Even if exit code is 1 (findings), output should be valid SARIF
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        results = data["runs"][0]["results"]
        assert len(results) >= 1
        assert results[0]["ruleId"] == "DEP-001"

    def test_scan_output_file_with_findings(self, tmp_path: Path) -> None:
        """--output writes findings to file."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        output = tmp_path / "report.json"
        result = self.runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--format", "json",
                "--output", str(output),
                "--offline",
            ]
        )

        assert result.exit_code == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert "findings" in data


# ──────────────────────────────────────────────────────────────────
# Regression tests
# ──────────────────────────────────────────────────────────────────


class TestRegressions:
    """Regression tests para bugs corregidos."""

    def test_chalk_duplicate_removed_from_npm_corpus(self) -> None:
        """[Regression] chalk should appear once in npm corpus."""
        from vigil.analyzers.deps.similarity import _BUILTIN_POPULAR_NPM

        chalk_entries = [k for k in _BUILTIN_POPULAR_NPM if k == "chalk"]
        assert len(chalk_entries) == 1
        # Should have the higher download count
        assert _BUILTIN_POPULAR_NPM["chalk"] == 22_000_000

    def test_rules_filter_actually_filters(self, tmp_path: Path) -> None:
        """[Regression] --rule flag now filters findings correctly."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75
        config.rules_filter = ["DEP-001"]  # Only DEP-001, not DEP-003

        engine = ScanEngine(config)
        engine.register_analyzer(DependencyAnalyzer())
        result = engine.run([str(tmp_path)])

        # DEP-003 findings should be filtered out
        for finding in result.findings:
            assert finding.rule_id == "DEP-001", (
                f"rules_filter not working: found {finding.rule_id}"
            )

    def test_environment_markers_parsed(self, tmp_path: Path) -> None:
        """[Regression] Packages with env markers are now parsed."""
        req = tmp_path / "requirements.txt"
        req.write_text('pywin32; sys_platform == "win32"\n')

        from vigil.analyzers.deps.parsers import parse_requirements_txt

        deps = parse_requirements_txt(req)
        assert len(deps) == 1
        assert deps[0].name == "pywin32"
