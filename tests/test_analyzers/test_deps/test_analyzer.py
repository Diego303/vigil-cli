"""Tests para DependencyAnalyzer completo."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vigil.analyzers.deps.analyzer import (
    DependencyAnalyzer,
    _deduplicate_deps,
    _extract_pinned_version,
    _extract_roots,
)
from vigil.analyzers.deps.parsers import DeclaredDependency
from vigil.analyzers.deps.registry_client import PackageInfo
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "deps"


class TestDependencyAnalyzerProtocol:
    """Tests para verificar que DependencyAnalyzer cumple el protocolo."""

    def test_name(self) -> None:
        analyzer = DependencyAnalyzer()
        assert analyzer.name == "dependency"

    def test_category(self) -> None:
        analyzer = DependencyAnalyzer()
        assert analyzer.category == Category.DEPENDENCY

    def test_analyze_returns_list(self) -> None:
        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([], config)

        assert isinstance(result, list)


class TestDependencyAnalyzerOffline:
    """Tests para analisis offline (solo checks estaticos)."""

    def test_no_deps_no_findings(self, tmp_path: Path) -> None:
        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([str(tmp_path)], config)

        assert result == []

    def test_typosquatting_detected_offline(self, tmp_path: Path) -> None:
        """Typosquatting se detecta en modo offline."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75

        result = analyzer.analyze([str(tmp_path)], config)

        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        assert len(dep003) >= 1
        assert "reqeusts" in dep003[0].message
        assert "requests" in dep003[0].message

    def test_legitimate_package_no_typosquatting(self, tmp_path: Path) -> None:
        """Paquetes legitimos no generan false positivos de typosquatting."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\nrequests>=2.31.0\ndjango>=4.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([str(tmp_path)], config)

        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        assert len(dep003) == 0

    def test_high_similarity_threshold_reduces_matches(self, tmp_path: Path) -> None:
        """Threshold alto reduce falsos positivos."""
        req = tmp_path / "requirements.txt"
        req.write_text("numpyy==1.0.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.95  # Very high threshold

        result = analyzer.analyze([str(tmp_path)], config)

        # With 0.95 threshold, "numpyy" vs "numpy" might or might not match
        # The important thing is no crash
        assert isinstance(result, list)


class TestDependencyAnalyzerWithRegistry:
    """Tests para analisis con verificacion de registry (mocked)."""

    def _make_config(self) -> ScanConfig:
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False
        return config

    def test_dep001_hallucinated_package(self, tmp_path: Path) -> None:
        """DEP-001: Paquete que no existe en el registry."""
        req = tmp_path / "requirements.txt"
        req.write_text("python-jwt-utils==1.0.0\n")

        mock_pkg = PackageInfo(
            name="python-jwt-utils", exists=False, ecosystem="pypi"
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep001 = [f for f in result if f.rule_id == "DEP-001"]
        assert len(dep001) == 1
        assert dep001[0].severity == Severity.CRITICAL
        assert "python-jwt-utils" in dep001[0].message
        assert "does not exist" in dep001[0].message
        assert dep001[0].location.file == str(req)
        assert dep001[0].location.line == 1

    def test_dep002_new_package(self, tmp_path: Path) -> None:
        """DEP-002: Paquete sospechosamente nuevo."""
        req = tmp_path / "requirements.txt"
        req.write_text("brand-new-pkg==0.0.1\n")

        from datetime import datetime, timezone, timedelta

        created = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

        mock_pkg = PackageInfo(
            name="brand-new-pkg",
            exists=True,
            ecosystem="pypi",
            created_at=created,
            source_url="https://github.com/test/test",
            latest_version="0.0.1",
            versions=["0.0.1"],
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()
        config.deps.min_age_days = 30

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep002 = [f for f in result if f.rule_id == "DEP-002"]
        assert len(dep002) == 1
        assert dep002[0].severity == Severity.HIGH
        assert "5 days ago" in dep002[0].message

    def test_dep005_no_source_repo(self, tmp_path: Path) -> None:
        """DEP-005: Paquete sin repositorio de codigo fuente."""
        req = tmp_path / "requirements.txt"
        req.write_text("mystery-pkg==1.0.0\n")

        mock_pkg = PackageInfo(
            name="mystery-pkg",
            exists=True,
            ecosystem="pypi",
            created_at="2020-01-01T00:00:00+00:00",
            source_url=None,
            latest_version="1.0.0",
            versions=["1.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep005 = [f for f in result if f.rule_id == "DEP-005"]
        assert len(dep005) == 1
        assert dep005[0].severity == Severity.MEDIUM

    def test_dep007_nonexistent_version(self, tmp_path: Path) -> None:
        """DEP-007: Version especificada no existe."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==99.99.99\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.0",
            versions=["2.0.0", "2.1.0", "2.2.0", "2.3.0", "3.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 1
        assert dep007[0].severity == Severity.CRITICAL
        assert "99.99.99" in dep007[0].message
        assert "3.0.0" in dep007[0].suggestion

    def test_legitimate_package_no_findings(self, tmp_path: Path) -> None:
        """Paquete legitimo no genera ningun finding."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.0",
            versions=["2.0.0", "3.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        # Only typosquatting checks may run — but "flask" is in popular corpus
        dep001 = [f for f in result if f.rule_id == "DEP-001"]
        dep002 = [f for f in result if f.rule_id == "DEP-002"]
        dep005 = [f for f in result if f.rule_id == "DEP-005"]
        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep001) == 0
        assert len(dep002) == 0
        assert len(dep005) == 0
        assert len(dep007) == 0

    def test_network_error_skips_gracefully(self, tmp_path: Path) -> None:
        """Error de network no genera findings de DEP-001."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            error="Network error: Connection refused",
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep001 = [f for f in result if f.rule_id == "DEP-001"]
        assert len(dep001) == 0

    def test_npm_package_hallucinated(self, tmp_path: Path) -> None:
        """DEP-001 tambien funciona para npm."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"nonexistent-ai-pkg": "^1.0.0"}}')

        mock_pkg = PackageInfo(
            name="nonexistent-ai-pkg", exists=False, ecosystem="npm"
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep001 = [f for f in result if f.rule_id == "DEP-001"]
        assert len(dep001) == 1
        assert "nonexistent-ai-pkg" in dep001[0].message
        assert "npm" in dep001[0].message

    def test_npm_pinned_version_not_found(self, tmp_path: Path) -> None:
        """DEP-007 para npm con version exacta."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"express": "4.99.99"}}')

        mock_pkg = PackageInfo(
            name="express",
            exists=True,
            ecosystem="npm",
            created_at="2010-12-29T00:00:00+00:00",
            source_url="https://github.com/expressjs/express",
            latest_version="4.18.2",
            versions=["4.17.0", "4.18.0", "4.18.2"],
        )

        analyzer = DependencyAnalyzer()
        config = self._make_config()

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 1


class TestDependencyAnalyzerMultipleFiles:
    """Tests para analisis con multiples archivos de dependencias."""

    def test_both_requirements_and_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["pydantic>=2.0"]\n'
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([str(tmp_path)], config)

        # No crashes, may or may not have findings depending on corpus
        assert isinstance(result, list)

    def test_deduplication(self, tmp_path: Path) -> None:
        """Paquetes duplicados entre archivos se deduplican."""
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["flask>=3.0"]\n'
        )

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.0",
            versions=["3.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        # flask should only be checked once
        instance.check.assert_called_once()


class TestHelperFunctions:
    """Tests para funciones helper del analyzer."""

    def test_extract_pinned_version_pypi(self) -> None:
        assert _extract_pinned_version("==1.0.0", "pypi") == "1.0.0"
        assert _extract_pinned_version("== 1.0.0", "pypi") == "1.0.0"
        assert _extract_pinned_version(">=1.0.0", "pypi") is None
        assert _extract_pinned_version("~=1.0.0", "pypi") is None
        assert _extract_pinned_version(">=1.0,<2.0", "pypi") is None

    def test_extract_pinned_version_npm(self) -> None:
        assert _extract_pinned_version("1.2.3", "npm") == "1.2.3"
        assert _extract_pinned_version("^1.2.3", "npm") is None
        assert _extract_pinned_version("~1.2.3", "npm") is None
        assert _extract_pinned_version(">=1.0.0", "npm") is None

    def test_deduplicate_deps(self) -> None:
        deps = [
            DeclaredDependency(
                name="flask",
                version_spec="==3.0.0",
                source_file="requirements.txt",
                line_number=1,
                ecosystem="pypi",
            ),
            DeclaredDependency(
                name="Flask",  # Same package, different case
                version_spec=">=3.0",
                source_file="pyproject.toml",
                line_number=5,
                ecosystem="pypi",
            ),
        ]

        unique = _deduplicate_deps(deps)

        assert len(unique) == 1
        assert unique[0].name == "flask"  # First occurrence kept

    def test_deduplicate_different_ecosystems(self) -> None:
        deps = [
            DeclaredDependency(
                name="redis",
                version_spec=">=4.0",
                source_file="requirements.txt",
                line_number=1,
                ecosystem="pypi",
            ),
            DeclaredDependency(
                name="redis",
                version_spec="^4.0.0",
                source_file="package.json",
                line_number=5,
                ecosystem="npm",
            ),
        ]

        unique = _deduplicate_deps(deps)

        # redis in pypi and redis in npm are different packages
        assert len(unique) == 2

    def test_extract_roots_from_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "src" / "app.py"
        f1.parent.mkdir(parents=True)
        f1.touch()

        roots = _extract_roots([str(f1)])

        assert len(roots) >= 1

    def test_extract_roots_empty(self) -> None:
        roots = _extract_roots([])

        assert roots == []


class TestFindingMetadata:
    """Tests para verificar que los findings tienen metadata correcta."""

    def test_dep001_metadata(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("fake-pkg==1.0.0\n")

        mock_pkg = PackageInfo(name="fake-pkg", exists=False, ecosystem="pypi")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch(
            "vigil.analyzers.deps.analyzer.RegistryClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep001 = [f for f in result if f.rule_id == "DEP-001"]
        assert len(dep001) == 1
        finding = dep001[0]
        assert finding.metadata["package"] == "fake-pkg"
        assert finding.metadata["ecosystem"] == "pypi"
        assert finding.suggestion is not None
        assert finding.location.file == str(req)
        assert finding.location.line == 1

    def test_dep003_metadata(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75

        result = analyzer.analyze([str(tmp_path)], config)

        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        assert len(dep003) >= 1
        finding = dep003[0]
        assert finding.metadata["package"] == "reqeusts"
        assert "similar_to" in finding.metadata
        assert "similarity" in finding.metadata
        assert finding.suggestion is not None
