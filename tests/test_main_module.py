"""Tests para __main__.py y BaseAnalyzer protocol."""

import subprocess
import sys

from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity


class TestMainModule:
    """Verifica que python -m vigil funciona."""

    def test_main_module_help(self):
        """python -m vigil --help funciona."""
        result = subprocess.run(
            [sys.executable, "-m", "vigil", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "vigil" in result.stdout
        assert "scan" in result.stdout

    def test_main_module_version(self):
        """python -m vigil --version funciona."""
        result = subprocess.run(
            [sys.executable, "-m", "vigil", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "vigil" in result.stdout


class TestBaseAnalyzerProtocol:
    """Verifica que los analyzers implementan el protocol correctamente."""

    def test_dependency_analyzer_conforms(self):
        """DependencyAnalyzer sigue el protocol BaseAnalyzer."""
        from vigil.analyzers.deps import DependencyAnalyzer
        analyzer = DependencyAnalyzer()
        assert hasattr(analyzer, "name")
        assert hasattr(analyzer, "category")
        assert hasattr(analyzer, "analyze")
        assert analyzer.name == "dependency"
        assert analyzer.category == Category.DEPENDENCY

    def test_auth_analyzer_conforms(self):
        """AuthAnalyzer sigue el protocol BaseAnalyzer."""
        from vigil.analyzers.auth import AuthAnalyzer
        analyzer = AuthAnalyzer()
        assert analyzer.name == "auth"
        assert analyzer.category == Category.AUTH

    def test_secrets_analyzer_conforms(self):
        """SecretsAnalyzer sigue el protocol BaseAnalyzer."""
        from vigil.analyzers.secrets import SecretsAnalyzer
        analyzer = SecretsAnalyzer()
        assert analyzer.name == "secrets"
        assert analyzer.category == Category.SECRETS

    def test_test_quality_analyzer_conforms(self):
        """TestQualityAnalyzer sigue el protocol BaseAnalyzer."""
        from vigil.analyzers.tests import TestQualityAnalyzer
        analyzer = TestQualityAnalyzer()
        assert analyzer.name == "test-quality"
        assert analyzer.category == Category.TEST_QUALITY

    def test_all_analyzers_return_findings_list(self, tmp_path):
        """Todos los analyzers retornan list[Finding]."""
        from vigil.analyzers.deps import DependencyAnalyzer
        from vigil.analyzers.auth import AuthAnalyzer
        from vigil.analyzers.secrets import SecretsAnalyzer
        from vigil.analyzers.tests import TestQualityAnalyzer

        (tmp_path / "app.py").write_text("x = 1")
        files = [str(tmp_path / "app.py")]
        config = ScanConfig(deps={"offline_mode": True})

        for AnalyzerClass in [DependencyAnalyzer, AuthAnalyzer, SecretsAnalyzer, TestQualityAnalyzer]:
            analyzer = AnalyzerClass()
            result = analyzer.analyze(files, config)
            assert isinstance(result, list)
            for f in result:
                assert isinstance(f, Finding)

    def test_custom_analyzer_protocol(self):
        """Un analyzer custom que sigue el protocol funciona con el engine."""
        from vigil.core.engine import ScanEngine

        class CustomAnalyzer:
            @property
            def name(self) -> str:
                return "custom"

            @property
            def category(self) -> Category:
                return Category.AUTH

            def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
                return [
                    Finding(
                        rule_id="CUSTOM-001",
                        category=Category.AUTH,
                        severity=Severity.LOW,
                        message="Custom finding",
                        location=Location(file="test.py", line=1),
                    )
                ]

        config = ScanConfig()
        engine = ScanEngine(config)
        engine.register_analyzer(CustomAnalyzer())
        # No files needed since analyzer ignores them
        result = engine.run([])
        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "CUSTOM-001"
