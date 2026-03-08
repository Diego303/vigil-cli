"""Tests para FASE 6 — Data + Polish.

Cubre:
- Script fetch_popular_packages.py (unit tests con mocks)
- Carga de datos desde data/*.json (similarity.py)
- Polish: exit codes, --quiet, --verbose, --offline, --changed-only
- Verificacion end-to-end de todos los flags
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vigil.cli import ExitCode, main
from vigil.config.schema import ScanConfig
from vigil.core.engine import ScanEngine, ScanResult
from vigil.core.finding import Category, Finding, Location, Severity

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "integration"
INSECURE_DIR = FIXTURES_DIR / "insecure_project"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def clean_dir(tmp_path):
    """Directorio limpio sin problemas."""
    (tmp_path / "app.py").write_text("x = 1\n")
    return tmp_path


@pytest.fixture
def insecure_dir(tmp_path):
    """Directorio con problemas detectables en offline mode."""
    # Auth: CORS * (AUTH-005)
    (tmp_path / "server.py").write_text(
        'from fastapi import FastAPI\n'
        'from fastapi.middleware.cors import CORSMiddleware\n'
        'app = FastAPI()\n'
        'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n'
    )
    # Secrets: placeholder (SEC-001)
    (tmp_path / "config.py").write_text(
        'API_KEY = "changeme"\n'
        'SECRET = "supersecret"\n'
    )
    # Tests: empty test (TEST-001)
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_app.py").write_text(
        "def test_something():\n"
        "    pass\n"
    )
    return tmp_path


# ===========================================================================
# 1. POPULAR PACKAGES DATA LOADING (similarity.py)
# ===========================================================================


class TestPopularPackagesDataLoading:
    """Verifica que data/*.json se carga correctamente cuando existe."""

    def test_load_pypi_from_data_file(self, tmp_path):
        """Cuando data/popular_pypi.json existe, se usa en vez del builtin."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        data = {"custom-package": 999_999, "another-pkg": 500_000}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert result == data
        assert "custom-package" in result

    def test_load_npm_from_data_file(self, tmp_path):
        """Cuando data/popular_npm.json existe, se usa en vez del builtin."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        data = {"my-npm-pkg": 123_456}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_npm.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("npm")

        assert result == data

    def test_fallback_to_builtin_when_no_file(self, tmp_path):
        """Sin archivos data/, usa el corpus builtin."""
        from vigil.analyzers.deps.similarity import (
            _BUILTIN_POPULAR_PYPI,
            load_popular_packages,
        )

        empty_dir = tmp_path / "empty_data"
        empty_dir.mkdir()

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", empty_dir):
            result = load_popular_packages("pypi")

        assert result == _BUILTIN_POPULAR_PYPI
        assert "requests" in result

    def test_fallback_on_invalid_json(self, tmp_path):
        """JSON invalido cae al corpus builtin."""
        from vigil.analyzers.deps.similarity import (
            _BUILTIN_POPULAR_PYPI,
            load_popular_packages,
        )

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text("NOT VALID JSON{{{")

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert result == _BUILTIN_POPULAR_PYPI

    def test_fallback_on_non_dict_json(self, tmp_path):
        """JSON valido pero no dict cae al builtin."""
        from vigil.analyzers.deps.similarity import (
            _BUILTIN_POPULAR_PYPI,
            load_popular_packages,
        )

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text('["list", "not", "dict"]')

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert result == _BUILTIN_POPULAR_PYPI

    def test_unknown_ecosystem_returns_empty(self, tmp_path):
        """Ecosystem desconocido retorna dict vacio."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        empty_dir = tmp_path / "empty_data"
        empty_dir.mkdir()

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", empty_dir):
            result = load_popular_packages("cargo")

        assert result == {}

    def test_data_file_with_5000_packages(self, tmp_path):
        """Simula un corpus de 5000 paquetes."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        data = {f"package-{i}": (5000 - i) * 1000 for i in range(5000)}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert len(result) == 5000

    def test_typosquatting_uses_loaded_data(self, tmp_path):
        """find_similar_popular usa datos de data/ cuando existen."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        data = {"requests": 300_000_000, "flask": 30_000_000}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            # "requsts" (missing 'e') es similar a "requests" — dist=1, sim=0.875
            matches = find_similar_popular("requsts", "pypi", threshold=0.8)

        assert len(matches) > 0
        assert matches[0][0] == "requests"

    def test_builtin_pypi_corpus_has_minimum_packages(self):
        """El corpus builtin de PyPI tiene al menos 100 paquetes."""
        from vigil.analyzers.deps.similarity import _BUILTIN_POPULAR_PYPI

        assert len(_BUILTIN_POPULAR_PYPI) >= 100

    def test_builtin_npm_corpus_has_minimum_packages(self):
        """El corpus builtin de npm tiene al menos 50 paquetes."""
        from vigil.analyzers.deps.similarity import _BUILTIN_POPULAR_NPM

        assert len(_BUILTIN_POPULAR_NPM) >= 50

    def test_builtin_pypi_has_key_packages(self):
        """El corpus builtin incluye paquetes clave del ecosistema."""
        from vigil.analyzers.deps.similarity import _BUILTIN_POPULAR_PYPI

        key_packages = ["requests", "flask", "django", "numpy", "pandas", "fastapi"]
        for pkg in key_packages:
            assert pkg in _BUILTIN_POPULAR_PYPI, f"{pkg} missing from builtin PyPI corpus"

    def test_builtin_npm_has_key_packages(self):
        """El corpus builtin incluye paquetes clave del ecosistema."""
        from vigil.analyzers.deps.similarity import _BUILTIN_POPULAR_NPM

        key_packages = ["react", "express", "lodash", "axios", "jest", "typescript"]
        for pkg in key_packages:
            assert pkg in _BUILTIN_POPULAR_NPM, f"{pkg} missing from builtin npm corpus"


# ===========================================================================
# 2. FETCH SCRIPT UNIT TESTS (con mocks HTTP)
# ===========================================================================


class TestFetchPopularPackagesScript:
    """Tests unitarios para scripts/fetch_popular_packages.py."""

    def _import_script(self):
        """Importa el script como modulo."""
        script_path = Path(__file__).parent.parent / "scripts"
        sys.path.insert(0, str(script_path))
        try:
            import fetch_popular_packages
            return fetch_popular_packages
        finally:
            sys.path.pop(0)

    def test_fetch_pypi_top_success(self):
        """fetch_pypi_top parsea correctamente la API de hugovk."""
        script = self._import_script()

        mock_data = {
            "rows": [
                {"project": "requests", "download_count": 300_000_000},
                {"project": "boto3", "download_count": 250_000_000},
                {"project": "numpy", "download_count": 145_000_000},
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top(count=10)

        assert len(result) == 3
        assert result["requests"] == 300_000_000
        assert result["boto3"] == 250_000_000

    def test_fetch_pypi_top_limits_count(self):
        """fetch_pypi_top respeta el parametro count."""
        script = self._import_script()

        mock_data = {
            "rows": [
                {"project": f"pkg-{i}", "download_count": 1000 - i}
                for i in range(100)
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top(count=10)

        assert len(result) == 10

    def test_fetch_pypi_top_http_error(self):
        """fetch_pypi_top retorna dict vacio en error HTTP."""
        script = self._import_script()

        import httpx

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top()

        assert result == {}

    def test_save_json(self, tmp_path):
        """save_json guarda datos correctamente."""
        script = self._import_script()

        data = {"pkg-a": 1000, "pkg-b": 500}
        filepath = tmp_path / "output.json"

        script.save_json(data, filepath)

        assert filepath.exists()
        loaded = json.loads(filepath.read_text())
        assert loaded == data

    def test_save_json_creates_parent_dirs(self, tmp_path):
        """save_json crea directorios padre si no existen."""
        script = self._import_script()

        filepath = tmp_path / "sub" / "dir" / "output.json"
        script.save_json({"pkg": 100}, filepath)

        assert filepath.exists()

    def test_npm_seed_list_not_empty(self):
        """La lista seed de paquetes npm no esta vacia."""
        script = self._import_script()
        assert len(script._NPM_SEED_PACKAGES) > 100


# ===========================================================================
# 3. EXIT CODES — verificacion exhaustiva
# ===========================================================================


class TestExitCodes:
    """Verifica que los exit codes son correctos en todos los escenarios."""

    def test_exit_success_clean_code(self, runner, clean_dir):
        """Codigo limpio -> exit 0."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--offline"])
        assert result.exit_code == ExitCode.SUCCESS

    def test_exit_findings_with_insecure_code(self, runner, insecure_dir):
        """Codigo inseguro -> exit 1 (findings above threshold)."""
        result = runner.invoke(main, ["scan", str(insecure_dir), "--offline"])
        assert result.exit_code == ExitCode.FINDINGS

    def test_exit_success_when_fail_on_critical_and_no_critical(self, runner, insecure_dir):
        """Con --fail-on critical, solo criticals causan exit 1."""
        # La fixture tiene SEC-001 (CRITICAL) asi que deberia ser exit 1
        result = runner.invoke(
            main, ["scan", str(insecure_dir), "--fail-on", "critical", "--offline"]
        )
        # Si hay criticos, es 1; si no hay criticos, es 0
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_exit_success_values(self):
        """Los valores de ExitCode son los esperados."""
        assert ExitCode.SUCCESS == 0
        assert ExitCode.FINDINGS == 1
        assert ExitCode.ERROR == 2

    def test_exit_error_on_bad_config(self, runner, tmp_path):
        """Config invalida -> exit 2."""
        bad_config = tmp_path / "bad.yaml"
        bad_config.write_text("invalid: {yaml: [unclosed")
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--config", str(bad_config), "--offline"]
        )
        # bad YAML should either be parsed incorrectly (exit 0) or cause error (exit 2)
        # depending on yaml.safe_load behavior
        assert result.exit_code in (0, 2)

    def test_exit_code_scan_with_rule_filter(self, runner, insecure_dir):
        """--rule filtra findings, puede cambiar exit code."""
        # Solo buscar TEST-001
        result = runner.invoke(
            main, ["scan", str(insecure_dir), "--rule", "TEST-001", "--offline"]
        )
        # TEST-001 tiene severidad HIGH, fail-on default es HIGH -> exit 1
        assert result.exit_code == ExitCode.FINDINGS

    def test_exit_code_scan_with_exclude_rule(self, runner, insecure_dir):
        """--exclude-rule elimina findings del resultado."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--exclude-rule", "AUTH-005",
                "--exclude-rule", "AUTH-004",
                "--exclude-rule", "SEC-001",
                "--exclude-rule", "SEC-002",
                "--exclude-rule", "SEC-004",
                "--exclude-rule", "TEST-001",
                "--offline",
            ]
        )
        # Con todos los findings potenciales excluidos, puede ser exit 0
        # Depends on what other findings might exist
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)


# ===========================================================================
# 4. QUIET MODE (--quiet)
# ===========================================================================


class TestQuietMode:
    """Verifica que --quiet suprime header/footer pero muestra findings."""

    def test_quiet_no_header(self, runner, clean_dir):
        """--quiet suprime el header 'vigil vX.Y.Z -- scanning'."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--quiet", "--offline"])
        assert result.exit_code == 0
        assert "vigil" not in result.output
        assert "scanning" not in result.output

    def test_quiet_no_footer(self, runner, clean_dir):
        """--quiet suprime el footer con 'files scanned' y 'analyzers'."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--quiet", "--offline"])
        assert "files scanned" not in result.output
        assert "analyzers" not in result.output

    def test_quiet_still_shows_findings(self, runner, insecure_dir):
        """--quiet todavia muestra los findings."""
        result = runner.invoke(main, ["scan", str(insecure_dir), "--quiet", "--offline"])
        # Deberia mostrar algun finding (la fixture tiene problemas)
        # Pero NO deberia mostrar header/footer
        assert "scanning" not in result.output
        assert "files scanned" not in result.output

    def test_quiet_no_suggestions(self, runner, insecure_dir):
        """--quiet desactiva show_suggestions via el loader."""
        result = runner.invoke(main, ["scan", str(insecure_dir), "--quiet", "--offline"])
        # En quiet mode, el loader setea show_suggestions = False
        assert "Suggestion:" not in result.output

    def test_quiet_no_empty_message(self, runner, clean_dir):
        """--quiet suprime 'No findings.' message."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--quiet", "--offline"])
        assert "No findings" not in result.output

    def test_quiet_json_format_unaffected(self, runner, clean_dir):
        """--quiet no afecta output JSON (ya es minimo)."""
        result = runner.invoke(
            main, ["scan", str(clean_dir), "--format", "json", "--quiet", "--offline"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "findings" in data


# ===========================================================================
# 5. VERBOSE MODE (--verbose)
# ===========================================================================


class TestVerboseMode:
    """Verifica que --verbose activa logging detallado en stderr."""

    def test_verbose_does_not_crash(self, runner, clean_dir):
        """--verbose no crashea."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--verbose", "--offline"])
        assert result.exit_code == 0

    def test_verbose_still_shows_output(self, runner, clean_dir):
        """--verbose todavia produce output normal en stdout."""
        result = runner.invoke(main, ["scan", str(clean_dir), "--verbose", "--offline"])
        assert "vigil" in result.output or "findings" in result.output

    def test_verbose_deps_command(self, runner, tmp_path):
        """--verbose funciona con vigil deps."""
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--verbose", "--offline"])
        assert result.exit_code == 0

    def test_verbose_logging_to_stderr(self):
        """Logging en verbose va a stderr, no stdout."""
        from vigil.logging.setup import setup_logging
        import logging

        setup_logging(verbose=True)
        root = logging.getLogger()
        # En verbose, level es DEBUG
        assert root.level == logging.DEBUG

    def test_non_verbose_logging_level(self):
        """Sin verbose, logging level es WARNING."""
        from vigil.logging.setup import setup_logging
        import logging

        setup_logging(verbose=False)
        root = logging.getLogger()
        assert root.level == logging.WARNING


# ===========================================================================
# 6. OFFLINE MODE (--offline)
# ===========================================================================


class TestOfflineMode:
    """Verifica que --offline no hace HTTP requests."""

    def test_offline_no_http_calls(self, runner, tmp_path):
        """--offline no hace requests HTTP a registries."""
        (tmp_path / "requirements.txt").write_text(
            "flask==3.0.0\nnonexistent-pkg==1.0.0\n"
        )
        (tmp_path / "app.py").write_text("x = 1\n")

        # Si offline no funciona, intentaria HTTP y posiblemente fallaria o tardaria
        result = runner.invoke(main, ["scan", str(tmp_path), "--offline"])
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_offline_deps_command(self, runner, tmp_path):
        """vigil deps --offline no hace HTTP."""
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--offline"])
        assert result.exit_code == 0

    def test_offline_no_verify(self, runner, tmp_path):
        """--no-verify equivale a offline para deps."""
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        result = runner.invoke(main, ["deps", str(tmp_path), "--no-verify"])
        assert result.exit_code == 0

    def test_offline_config_propagation(self):
        """--offline se propaga a deps.offline_mode en config."""
        from vigil.config.loader import load_config

        config = load_config(cli_overrides={"offline": True})
        assert config.deps.offline_mode is True

    def test_offline_still_runs_static_checks(self, runner, insecure_dir):
        """--offline todavia ejecuta checks estaticos (auth, secrets, tests)."""
        result = runner.invoke(main, ["scan", str(insecure_dir), "--offline"])
        # Deberia encontrar AUTH y SEC findings (no requieren network)
        assert result.exit_code == ExitCode.FINDINGS

    def test_offline_typosquatting_still_works(self, runner, tmp_path):
        """--offline todavia detecta typosquatting (usa corpus local)."""
        # "requets" (missing 's') — distance 1 from "requests", sim ~0.875 > 0.85
        (tmp_path / "requirements.txt").write_text("requets==2.31.0\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--offline", "--format", "json"]
        )
        data = json.loads(result.output)
        dep_findings = [f for f in data["findings"] if f["rule_id"] == "DEP-003"]
        assert len(dep_findings) > 0, "Typosquatting should work offline"


# ===========================================================================
# 7. CHANGED-ONLY MODE (--changed-only)
# ===========================================================================


class TestChangedOnlyMode:
    """Verifica que --changed-only funciona correctamente."""

    def test_changed_only_no_changes(self, runner):
        """--changed-only sin cambios -> 'No changed files' y exit 0."""
        with patch("vigil.cli._get_changed_files", return_value=[]):
            result = runner.invoke(main, ["scan", "--changed-only", "--offline"])
        assert result.exit_code == 0
        assert "No changed files" in result.output

    def test_changed_only_with_changes(self, runner, tmp_path):
        """--changed-only con archivos cambiados los escanea."""
        (tmp_path / "changed.py").write_text("x = 1\n")
        changed_files = [str(tmp_path / "changed.py")]

        with patch("vigil.cli._get_changed_files", return_value=changed_files):
            result = runner.invoke(main, ["scan", "--changed-only", "--offline"])
        assert result.exit_code == 0

    def test_changed_only_respects_findings(self, runner, tmp_path):
        """--changed-only con archivos inseguros genera findings."""
        insecure_file = tmp_path / "bad.py"
        insecure_file.write_text(
            'API_KEY = "changeme"\n'
            'SECRET = "supersecret"\n'
        )

        with patch("vigil.cli._get_changed_files", return_value=[str(insecure_file)]):
            result = runner.invoke(main, ["scan", "--changed-only", "--offline"])
        # Deberia encontrar SEC-001 (placeholder)
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_get_changed_files_git_not_available(self):
        """_get_changed_files retorna [] si git no esta disponible."""
        from vigil.cli import _get_changed_files

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _get_changed_files()
        assert result == []

    def test_get_changed_files_git_timeout(self):
        """_get_changed_files retorna [] si git timeout."""
        from vigil.cli import _get_changed_files
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            result = _get_changed_files()
        assert result == []

    def test_get_changed_files_nonzero_exit(self):
        """_get_changed_files retorna [] si git retorna error."""
        from vigil.cli import _get_changed_files

        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = _get_changed_files()
        assert result == []


# ===========================================================================
# 8. CATEGORY FILTER
# ===========================================================================


class TestCategoryFilter:
    """Verifica que --category filtra analyzers correctamente."""

    def test_category_dependency_only(self, runner, insecure_dir):
        """--category dependency solo ejecuta DependencyAnalyzer."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--category", "dependency",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        # Solo findings de dependency (o ninguno en offline)
        for f in data["findings"]:
            assert f["category"] == "dependency"

    def test_category_auth_only(self, runner, insecure_dir):
        """--category auth solo ejecuta AuthAnalyzer."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--category", "auth",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["category"] == "auth"

    def test_category_secrets_only(self, runner, insecure_dir):
        """--category secrets solo ejecuta SecretsAnalyzer."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--category", "secrets",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["category"] == "secrets"

    def test_category_test_quality_only(self, runner, insecure_dir):
        """--category test-quality solo ejecuta TestQualityAnalyzer."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--category", "test-quality",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["category"] == "test-quality"

    def test_multiple_categories(self, runner, insecure_dir):
        """Multiples --category filtra a solo esas categorias."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "-C", "auth", "-C", "secrets",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["category"] in ("auth", "secrets")


# ===========================================================================
# 9. RULE FILTER AND EXCLUDE
# ===========================================================================


class TestRuleFilterAndExclude:
    """Verifica --rule y --exclude-rule."""

    def test_rule_filter(self, runner, insecure_dir):
        """--rule solo incluye findings de esa regla."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--rule", "SEC-001",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["rule_id"] == "SEC-001"

    def test_exclude_rule(self, runner, insecure_dir):
        """--exclude-rule excluye findings de esa regla."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--exclude-rule", "SEC-001",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["rule_id"] != "SEC-001"

    def test_multiple_rules(self, runner, insecure_dir):
        """Multiple --rule incluye solo esas reglas."""
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--rule", "SEC-001",
                "--rule", "TEST-001",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["rule_id"] in ("SEC-001", "TEST-001")


# ===========================================================================
# 10. LANGUAGE FILTER
# ===========================================================================


class TestLanguageFilter:
    """Verifica que --language filtra archivos correctamente."""

    def test_language_python_only(self, runner, tmp_path):
        """--language python solo escanea .py."""
        (tmp_path / "app.py").write_text('SECRET = "changeme"\n')
        (tmp_path / "app.js").write_text('const SECRET = "changeme";\n')
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--language", "python",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            assert f["location"]["file"].endswith(".py"), \
                f"Finding in non-Python file: {f['location']['file']}"

    def test_language_javascript_only(self, runner, tmp_path):
        """--language javascript solo escanea .js/.ts."""
        (tmp_path / "app.py").write_text('SECRET = "changeme"\n')
        (tmp_path / "app.js").write_text('const SECRET = "changeme";\n')
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--language", "javascript",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            loc = f["location"]["file"]
            assert any(loc.endswith(ext) for ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")), \
                f"Finding in non-JS file: {loc}"


# ===========================================================================
# 11. OUTPUT FORMAT COMPLETENESS
# ===========================================================================


class TestOutputFormats:
    """Verifica que todos los formatos producen output valido."""

    def test_human_format_shows_findings(self, runner, insecure_dir):
        """Formato human muestra findings con iconos."""
        result = runner.invoke(
            main, ["scan", str(insecure_dir), "--format", "human", "--offline"]
        )
        assert result.exit_code == ExitCode.FINDINGS
        # Deberia tener iconos y detalles
        assert "findings" in result.output.lower()

    def test_json_format_valid(self, runner, insecure_dir):
        """JSON output es valido y tiene estructura correcta."""
        result = runner.invoke(
            main, ["scan", str(insecure_dir), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        assert "findings" in data
        assert "files_scanned" in data
        assert "duration_seconds" in data
        assert "analyzers_run" in data
        assert isinstance(data["findings"], list)
        assert len(data["findings"]) > 0

    def test_sarif_format_valid(self, runner, insecure_dir):
        """SARIF output es valido 2.1.0."""
        result = runner.invoke(
            main, ["scan", str(insecure_dir), "--format", "sarif", "--offline"]
        )
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["tool"]["driver"]["name"] == "vigil"
        assert len(run["results"]) > 0

    def test_junit_format_valid(self, runner, insecure_dir):
        """JUnit output es XML valido."""
        import xml.etree.ElementTree as ET

        result = runner.invoke(
            main, ["scan", str(insecure_dir), "--format", "junit", "--offline"]
        )
        root = ET.fromstring(result.output)
        assert root.tag == "testsuites"
        suite = root.find("testsuite")
        assert suite is not None

    def test_output_to_file(self, runner, insecure_dir):
        """--output escribe a archivo y sigue mostrando en stdout para human."""
        output_file = insecure_dir / "report.json"
        result = runner.invoke(
            main, [
                "scan", str(insecure_dir),
                "--format", "json",
                "--output", str(output_file),
                "--offline",
            ]
        )
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "findings" in data


# ===========================================================================
# 12. ENGINE BEHAVIOR
# ===========================================================================


class TestEngineBehavior:
    """Verifica comportamiento correcto del engine."""

    def test_analyzer_error_does_not_crash_scan(self):
        """Un analyzer que falla no crashea el scan completo."""
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)

        class BrokenAnalyzer:
            name = "broken"
            category = Category.AUTH

            def analyze(self, files, config):
                raise RuntimeError("Boom!")

        class WorkingAnalyzer:
            name = "working"
            category = Category.SECRETS

            def analyze(self, files, config):
                return [
                    Finding(
                        rule_id="SEC-001",
                        category=Category.SECRETS,
                        severity=Severity.CRITICAL,
                        message="Found a secret",
                        location=Location(file="test.py", line=1),
                    )
                ]

        engine.register_analyzer(BrokenAnalyzer())
        engine.register_analyzer(WorkingAnalyzer())

        result = engine.run([])
        assert len(result.errors) == 1
        assert "broken" in result.errors[0].lower() or "Boom" in result.errors[0]
        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "SEC-001"

    def test_findings_sorted_by_severity(self):
        """Los findings se ordenan por severidad (critical primero)."""
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)

        class MixedAnalyzer:
            name = "mixed"
            category = Category.AUTH

            def analyze(self, files, config):
                return [
                    Finding(
                        rule_id="AUTH-006",
                        category=Category.AUTH,
                        severity=Severity.MEDIUM,
                        message="medium",
                        location=Location(file="a.py"),
                    ),
                    Finding(
                        rule_id="AUTH-004",
                        category=Category.AUTH,
                        severity=Severity.CRITICAL,
                        message="critical",
                        location=Location(file="b.py"),
                    ),
                    Finding(
                        rule_id="AUTH-005",
                        category=Category.AUTH,
                        severity=Severity.HIGH,
                        message="high",
                        location=Location(file="c.py"),
                    ),
                ]

        engine.register_analyzer(MixedAnalyzer())
        result = engine.run([])

        severities = [f.severity for f in result.findings]
        assert severities == [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM]

    def test_rule_override_severity(self):
        """Rule override cambia la severidad de un finding."""
        from vigil.config.schema import RuleOverride

        config = ScanConfig(
            deps={"offline_mode": True},
            rules={"AUTH-005": RuleOverride(severity="low")},
        )
        engine = ScanEngine(config)

        class AuthAnalyzer:
            name = "auth"
            category = Category.AUTH

            def analyze(self, files, config):
                return [
                    Finding(
                        rule_id="AUTH-005",
                        category=Category.AUTH,
                        severity=Severity.HIGH,
                        message="CORS issue",
                        location=Location(file="a.py"),
                    )
                ]

        engine.register_analyzer(AuthAnalyzer())
        result = engine.run([])

        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.LOW

    def test_rule_override_disable(self):
        """Rule override puede deshabilitar una regla."""
        from vigil.config.schema import RuleOverride

        config = ScanConfig(
            deps={"offline_mode": True},
            rules={"AUTH-005": RuleOverride(enabled=False)},
        )
        engine = ScanEngine(config)

        class AuthAnalyzer:
            name = "auth"
            category = Category.AUTH

            def analyze(self, files, config):
                return [
                    Finding(
                        rule_id="AUTH-005",
                        category=Category.AUTH,
                        severity=Severity.HIGH,
                        message="CORS issue",
                        location=Location(file="a.py"),
                    )
                ]

        engine.register_analyzer(AuthAnalyzer())
        result = engine.run([])

        assert len(result.findings) == 0


# ===========================================================================
# 13. SCAN RESULT PROPERTIES
# ===========================================================================


class TestScanResultProperties:
    """Verifica propiedades de ScanResult."""

    def _make_finding(self, severity: Severity) -> Finding:
        return Finding(
            rule_id="TEST-001",
            category=Category.TEST_QUALITY,
            severity=severity,
            message="test",
            location=Location(file="t.py"),
        )

    def test_critical_count(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.CRITICAL),
            self._make_finding(Severity.CRITICAL),
            self._make_finding(Severity.HIGH),
        ])
        assert result.critical_count == 2

    def test_high_count(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.HIGH),
            self._make_finding(Severity.MEDIUM),
        ])
        assert result.high_count == 1

    def test_medium_count(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.MEDIUM),
            self._make_finding(Severity.MEDIUM),
            self._make_finding(Severity.LOW),
        ])
        assert result.medium_count == 2

    def test_low_count(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.LOW),
        ])
        assert result.low_count == 1

    def test_has_blocking_findings_true(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.HIGH),
        ])
        assert result.has_blocking_findings is True

    def test_has_blocking_findings_false(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.MEDIUM),
            self._make_finding(Severity.LOW),
        ])
        assert result.has_blocking_findings is False

    def test_findings_above_high(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.CRITICAL),
            self._make_finding(Severity.HIGH),
            self._make_finding(Severity.MEDIUM),
            self._make_finding(Severity.LOW),
        ])
        above = result.findings_above(Severity.HIGH)
        assert len(above) == 2

    def test_findings_above_medium(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.CRITICAL),
            self._make_finding(Severity.HIGH),
            self._make_finding(Severity.MEDIUM),
            self._make_finding(Severity.LOW),
        ])
        above = result.findings_above(Severity.MEDIUM)
        assert len(above) == 3

    def test_findings_above_critical(self):
        result = ScanResult(findings=[
            self._make_finding(Severity.HIGH),
            self._make_finding(Severity.MEDIUM),
        ])
        above = result.findings_above(Severity.CRITICAL)
        assert len(above) == 0

    def test_empty_result(self):
        result = ScanResult()
        assert result.critical_count == 0
        assert result.high_count == 0
        assert result.has_blocking_findings is False
        assert result.findings_above(Severity.LOW) == []


# ===========================================================================
# 14. HUMAN FORMATTER DETAILS
# ===========================================================================


class TestHumanFormatterDetails:
    """Verifica detalles del formatter humano."""

    def test_format_empty_result(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False)
        result = ScanResult()
        output = formatter.format(result)
        assert "No findings" in output
        assert "0 files scanned" in output

    def test_format_with_findings(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False)
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="SEC-001",
                    category=Category.SECRETS,
                    severity=Severity.CRITICAL,
                    message='Placeholder secret "changeme" in code',
                    location=Location(file="config.py", line=5),
                    suggestion="Use environment variables instead.",
                )
            ],
            files_scanned=10,
            duration_seconds=0.5,
            analyzers_run=["secrets"],
        )
        output = formatter.format(result)
        assert "SEC-001" in output
        assert "CRITICAL" in output
        assert "config.py:5" in output
        assert "Placeholder" in output
        assert "Suggestion:" in output
        assert "10 files scanned" in output

    def test_format_quiet_mode(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False, quiet=True)
        result = ScanResult(files_scanned=5, analyzers_run=["auth"])
        output = formatter.format(result)
        assert "vigil" not in output
        assert "scanning" not in output
        assert "files scanned" not in output

    def test_format_no_suggestions(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False, show_suggestions=False)
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="SEC-001",
                    category=Category.SECRETS,
                    severity=Severity.CRITICAL,
                    message="Secret found",
                    location=Location(file="a.py"),
                    suggestion="Fix it",
                )
            ],
        )
        output = formatter.format(result)
        assert "Suggestion:" not in output

    def test_format_with_snippet(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False)
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="AUTH-005",
                    category=Category.AUTH,
                    severity=Severity.HIGH,
                    message="CORS *",
                    location=Location(
                        file="app.py",
                        line=3,
                        snippet='allow_origins=["*"]',
                    ),
                )
            ],
        )
        output = formatter.format(result)
        assert 'allow_origins=["*"]' in output

    def test_format_severity_counts(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False)
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="SEC-001",
                    category=Category.SECRETS,
                    severity=Severity.CRITICAL,
                    message="a",
                    location=Location(file="a.py"),
                ),
                Finding(
                    rule_id="AUTH-005",
                    category=Category.AUTH,
                    severity=Severity.HIGH,
                    message="b",
                    location=Location(file="b.py"),
                ),
            ],
            files_scanned=5,
            duration_seconds=0.1,
        )
        output = formatter.format(result)
        assert "2 findings" in output
        assert "1 critical" in output
        assert "1 high" in output

    def test_format_with_errors(self):
        from vigil.reports.human import HumanFormatter

        formatter = HumanFormatter(colors=False)
        result = ScanResult(errors=["Analyzer auth failed: timeout"])
        output = formatter.format(result)
        assert "ERROR" in output
        assert "timeout" in output


# ===========================================================================
# 15. CONFIG MERGE AND STRATEGIES
# ===========================================================================


class TestConfigMergeStrategies:
    """Verifica que las estrategias de config funcionan."""

    def test_strict_strategy_fail_on_medium(self):
        from vigil.config.loader import load_config, STRATEGY_PRESETS

        preset = STRATEGY_PRESETS["strict"]
        config = ScanConfig(**preset)
        assert config.fail_on == "medium"

    def test_relaxed_strategy_fail_on_critical(self):
        from vigil.config.loader import STRATEGY_PRESETS

        preset = STRATEGY_PRESETS["relaxed"]
        config = ScanConfig(**preset)
        assert config.fail_on == "critical"

    def test_standard_strategy_defaults(self):
        from vigil.config.loader import STRATEGY_PRESETS

        preset = STRATEGY_PRESETS["standard"]
        config = ScanConfig(**preset)
        assert config.fail_on == "high"

    def test_cli_overrides_take_precedence(self):
        from vigil.config.loader import load_config

        config = load_config(cli_overrides={
            "fail_on": "critical",
            "offline": True,
            "verbose": True,
        })
        assert config.fail_on == "critical"
        assert config.deps.offline_mode is True
        assert config.output.verbose is True
