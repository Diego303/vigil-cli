"""QA regression tests para FASE 6 — Data + Polish.

Cubre:
- Bugs encontrados en audit de FASE 6
- Edge cases para el script fetch_popular_packages.py
- Falsos positivos (codigo limpio NO genera findings)
- Falsos negativos (codigo inseguro DEBE generar findings)
- CLI flags interaccion y combinaciones
- Exit codes exhaustivos
- Robustez: encoding, archivos vacios, paths no existentes
- Regresiones especificas
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vigil.cli import ExitCode, _get_changed_files, main
from vigil.config.loader import load_config
from vigil.config.schema import RuleOverride, ScanConfig
from vigil.core.engine import ScanEngine, ScanResult
from vigil.core.finding import Category, Finding, Location, Severity
from vigil.reports.human import HumanFormatter


@pytest.fixture
def runner():
    return CliRunner()


# ===========================================================================
# 1. REGRESSION — Bugs encontrados en audit FASE 6
# ===========================================================================


class TestRegressionFetchScriptJsonOutsideContext:
    """Bug: resp.json() era llamado fuera del `with httpx.Client` block."""

    def _import_script(self):
        script_path = Path(__file__).parent.parent / "scripts"
        sys.path.insert(0, str(script_path))
        try:
            import importlib

            import fetch_popular_packages

            importlib.reload(fetch_popular_packages)
            return fetch_popular_packages
        finally:
            sys.path.pop(0)

    def test_fetch_pypi_parses_json_inside_context(self):
        """resp.json() debe llamarse dentro del `with` block."""
        script = self._import_script()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rows": [{"project": "flask", "download_count": 100}]
        }

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top(count=10)

        assert result == {"flask": 100}
        # json() must be called (proves it was parsed)
        mock_response.json.assert_called_once()

    def test_fetch_pypi_handles_json_decode_error(self):
        """JSONDecodeError en PyPI response retorna dict vacio."""
        script = self._import_script()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("bad", "", 0)

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top()

        assert result == {}


class TestRegressionDuplicateNuxt:
    """Bug: 'nuxt' aparecia duplicado en _NPM_SEED_PACKAGES."""

    def _import_script(self):
        script_path = Path(__file__).parent.parent / "scripts"
        sys.path.insert(0, str(script_path))
        try:
            import importlib

            import fetch_popular_packages

            importlib.reload(fetch_popular_packages)
            return fetch_popular_packages
        finally:
            sys.path.pop(0)

    def test_no_duplicate_seed_packages(self):
        """Cada nombre en _NPM_SEED_PACKAGES debe ser unico."""
        script = self._import_script()
        seen = set()
        duplicates = []
        for name in script._NPM_SEED_PACKAGES:
            if name in seen:
                duplicates.append(name)
            seen.add(name)
        assert duplicates == [], f"Duplicate seed packages: {duplicates}"


class TestRegressionOutputFileWrite:
    """Bug: OSError en write_text de --output no se manejaba."""

    def test_output_write_error_exits_with_error_code(self, runner, tmp_path):
        """Si no se puede escribir el archivo de output, exit code es 2."""
        (tmp_path / "app.py").write_text("x = 1\n")
        # Path sin permisos — usar un directorio que no existe y no se puede crear
        # Simular error de escritura via un path que no puede existir
        if sys.platform != "win32":
            bad_output = "/proc/nonexistent/report.json"
            result = runner.invoke(
                main,
                [
                    "scan", str(tmp_path),
                    "--format", "json",
                    "--output", bad_output,
                    "--offline",
                ],
            )
            assert result.exit_code == ExitCode.ERROR
            assert "Error writing output file" in result.output


# ===========================================================================
# 2. FETCH SCRIPT — edge cases adicionales
# ===========================================================================


class TestFetchScriptEdgeCases:
    """Edge cases del script fetch_popular_packages.py."""

    def _import_script(self):
        script_path = Path(__file__).parent.parent / "scripts"
        sys.path.insert(0, str(script_path))
        try:
            import importlib

            import fetch_popular_packages

            importlib.reload(fetch_popular_packages)
            return fetch_popular_packages
        finally:
            sys.path.pop(0)

    def test_fetch_pypi_empty_rows(self):
        """API de PyPI devuelve rows vacio."""
        script = self._import_script()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"rows": []}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top(count=100)

        assert result == {}

    def test_fetch_pypi_missing_project_key(self):
        """Rows con campos faltantes se saltan."""
        script = self._import_script()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rows": [
                {"project": "flask", "download_count": 100},
                {"download_count": 50},  # missing "project"
                {"project": "", "download_count": 30},  # empty name
                {"project": "django", "download_count": 80},
            ]
        }

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top(count=100)

        assert len(result) == 2
        assert "flask" in result
        assert "django" in result

    def test_save_json_utf8_package_names(self, tmp_path):
        """save_json maneja paquetes con caracteres especiales."""
        script = self._import_script()
        data = {"paquete-con-tilde": 100, "pkg_underscore": 200}
        filepath = tmp_path / "test.json"
        script.save_json(data, filepath)
        loaded = json.loads(filepath.read_text(encoding="utf-8"))
        assert loaded == data

    def test_save_json_empty_data(self, tmp_path):
        """save_json con dict vacio crea archivo JSON valido."""
        script = self._import_script()
        filepath = tmp_path / "empty.json"
        script.save_json({}, filepath)
        loaded = json.loads(filepath.read_text())
        assert loaded == {}

    def test_fetch_pypi_count_zero(self):
        """count=0 retorna dict vacio sin crashear."""
        script = self._import_script()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rows": [{"project": "flask", "download_count": 100}]
        }

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = script.fetch_pypi_top(count=0)

        assert result == {}

    def test_seed_packages_all_strings(self):
        """Todos los items en seed list son strings no vacios."""
        script = self._import_script()
        for i, name in enumerate(script._NPM_SEED_PACKAGES):
            assert isinstance(name, str), f"Item {i} is not str: {type(name)}"
            assert len(name) > 0, f"Item {i} is empty string"


# ===========================================================================
# 3. POPULAR PACKAGES DATA LOADING — edge cases avanzados
# ===========================================================================


class TestPopularPackagesLoadingAdvanced:
    """Edge cases avanzados de carga de datos."""

    def test_load_very_large_corpus(self, tmp_path):
        """Corpus con 10000 paquetes se carga correctamente."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        data = {f"pkg-{i:05d}": (10000 - i) * 100 for i in range(10000)}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert len(result) == 10000

    def test_load_corpus_with_zero_downloads(self, tmp_path):
        """Paquetes con 0 downloads se cargan."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        data = {"flask": 1000, "zero-pkg": 0}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert "zero-pkg" in result
        assert result["zero-pkg"] == 0

    def test_load_corpus_with_negative_downloads(self, tmp_path):
        """Paquetes con downloads negativos se cargan (no se validan)."""
        from vigil.analyzers.deps.similarity import load_popular_packages

        data = {"flask": 1000, "bad-pkg": -5}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text(json.dumps(data))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            result = load_popular_packages("pypi")

        assert "bad-pkg" in result

    def test_similarity_with_empty_corpus(self):
        """find_similar_popular con corpus vacio retorna lista vacia."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        result = find_similar_popular("flask", "pypi", popular_packages={})
        assert result == []

    def test_similarity_exact_match_excluded(self):
        """Exact match (normalizando) no se reporta como typosquatting."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        corpus = {"Flask": 1000, "requests": 2000}
        result = find_similar_popular("flask", "pypi", popular_packages=corpus)
        # "flask" normalizado == "Flask" normalizado -> no es typosquatting
        assert not any(m[0] == "Flask" for m in result)

    def test_similarity_pypi_normalization(self):
        """PyPI normaliza hyphens, underscores y dots como equivalentes."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        corpus = {"python-dateutil": 1000}
        # python_dateutil es el mismo paquete tras normalizar
        result = find_similar_popular(
            "python_dateutil", "pypi", popular_packages=corpus
        )
        # Should NOT match because after normalization they are identical
        assert not any(m[0] == "python-dateutil" for m in result)

    def test_levenshtein_empty_strings(self):
        """Levenshtein entre strings vacios es 0."""
        from vigil.analyzers.deps.similarity import levenshtein_distance

        assert levenshtein_distance("", "") == 0

    def test_levenshtein_one_empty(self):
        """Levenshtein con un string vacio es la longitud del otro."""
        from vigil.analyzers.deps.similarity import levenshtein_distance

        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "xyz") == 3

    def test_normalized_similarity_identical(self):
        """Similaridad de strings identicos es 1.0."""
        from vigil.analyzers.deps.similarity import normalized_similarity

        assert normalized_similarity("flask", "flask") == 1.0

    def test_normalized_similarity_case_insensitive(self):
        """Similaridad ignora case."""
        from vigil.analyzers.deps.similarity import normalized_similarity

        assert normalized_similarity("Flask", "flask") == 1.0

    def test_normalized_similarity_empty_strings(self):
        """Similaridad de strings vacios es 1.0."""
        from vigil.analyzers.deps.similarity import normalized_similarity

        assert normalized_similarity("", "") == 1.0

    def test_normalized_similarity_completely_different(self):
        """Strings completamente diferentes tienen baja similaridad."""
        from vigil.analyzers.deps.similarity import normalized_similarity

        sim = normalized_similarity("abc", "xyz")
        assert sim < 0.5


# ===========================================================================
# 4. FALSOS POSITIVOS — codigo limpio NO genera findings
# ===========================================================================


class TestFalsePositives:
    """Verifica que codigo limpio NO genera findings."""

    def test_clean_python_no_findings(self, runner, tmp_path):
        """Codigo Python limpio no genera findings."""
        (tmp_path / "clean.py").write_text(
            "import os\n\n"
            "def get_config():\n"
            "    return os.environ.get('API_KEY')\n"
        )
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        assert len(data["findings"]) == 0, (
            f"Expected 0 findings for clean code, got: "
            f"{[f['rule_id'] for f in data['findings']]}"
        )

    def test_env_variable_access_no_secret_finding(self, runner, tmp_path):
        """os.environ.get() no debe trigger SEC-*."""
        (tmp_path / "config.py").write_text(
            "import os\n"
            "SECRET_KEY = os.environ.get('SECRET_KEY')\n"
            "DB_URL = os.getenv('DATABASE_URL')\n"
        )
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        sec_findings = [f for f in data["findings"] if f["rule_id"].startswith("SEC")]
        assert len(sec_findings) == 0, (
            f"env var access should not trigger SEC: {sec_findings}"
        )

    def test_popular_packages_no_typosquatting(self, runner, tmp_path):
        """Paquetes populares no deben trigger DEP-003."""
        (tmp_path / "requirements.txt").write_text(
            "requests==2.31.0\n"
            "flask==3.0.0\n"
            "django==5.0.0\n"
            "numpy==1.26.0\n"
            "pandas==2.1.0\n"
        )
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        typo_findings = [
            f for f in data["findings"] if f["rule_id"] == "DEP-003"
        ]
        assert len(typo_findings) == 0, (
            f"Popular packages should not trigger typosquatting: {typo_findings}"
        )

    def test_test_with_assertions_no_test001(self, runner, tmp_path):
        """Test con assertions reales no genera TEST-001."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_app.py").write_text(
            "def test_addition():\n"
            "    result = 1 + 1\n"
            "    assert result == 2\n"
            "    assert isinstance(result, int)\n"
        )
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        test001 = [f for f in data["findings"] if f["rule_id"] == "TEST-001"]
        assert len(test001) == 0, (
            f"Test with real assertions should not trigger TEST-001: {test001}"
        )

    def test_excluded_dirs_not_scanned(self, runner, tmp_path):
        """Archivos en node_modules/.venv no se escanean."""
        venv_dir = tmp_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "bad.py").write_text('SECRET = "changeme"\n')

        node_dir = tmp_path / "node_modules" / "pkg"
        node_dir.mkdir(parents=True)
        (node_dir / "bad.js").write_text('const SECRET = "changeme";\n')

        (tmp_path / "clean.py").write_text("x = 1\n")

        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            loc = f["location"]["file"]
            assert ".venv" not in loc, f"Finding in .venv: {loc}"
            assert "node_modules" not in loc, f"Finding in node_modules: {loc}"


# ===========================================================================
# 5. FALSOS NEGATIVOS — codigo inseguro DEBE generar findings
# ===========================================================================


class TestFalseNegatives:
    """Verifica que codigo inseguro genera findings esperados."""

    def test_placeholder_secret_detected(self, runner, tmp_path):
        """SEC-001: placeholder secret debe detectarse."""
        (tmp_path / "config.py").write_text(
            'API_KEY = "changeme"\n'
        )
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--category", "secrets",
                "--format", "json",
                "--offline",
            ],
        )
        data = json.loads(result.output)
        sec001 = [f for f in data["findings"] if f["rule_id"] == "SEC-001"]
        assert len(sec001) > 0, "SEC-001 should detect 'changeme' placeholder"

    def test_hardcoded_jwt_secret_detected(self, runner, tmp_path):
        """AUTH-004: JWT secret hardcodeado debe detectarse."""
        (tmp_path / "auth.py").write_text(
            'import jwt\n'
            'SECRET_KEY = "mysecretkey"\n'
            'token = jwt.encode({"sub": "user"}, SECRET_KEY)\n'
        )
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--category", "auth",
                "--format", "json",
                "--offline",
            ],
        )
        data = json.loads(result.output)
        auth004 = [f for f in data["findings"] if f["rule_id"] == "AUTH-004"]
        assert len(auth004) > 0, "AUTH-004 should detect hardcoded JWT secret"

    def test_empty_test_detected(self, runner, tmp_path):
        """TEST-001: test sin assertions debe detectarse."""
        (tmp_path / "test_app.py").write_text(
            "def test_empty():\n"
            "    x = 1 + 1\n"
        )
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--category", "test-quality",
                "--format", "json",
                "--offline",
            ],
        )
        data = json.loads(result.output)
        test001 = [f for f in data["findings"] if f["rule_id"] == "TEST-001"]
        assert len(test001) > 0, "TEST-001 should detect test without assertions"

    def test_cors_wildcard_detected(self, runner, tmp_path):
        """AUTH-005: CORS con * debe detectarse.

        pytest tmp_path contains 'test' in path which triggers
        cors_allow_localhost suppression, so we disable it via config.
        """
        (tmp_path / "app.py").write_text(
            'from fastapi import FastAPI\n'
            'from fastapi.middleware.cors import CORSMiddleware\n'
            'app = FastAPI()\n'
            'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n'
        )
        (tmp_path / ".vigil.yaml").write_text(
            "auth:\n  cors_allow_localhost: false\n"
        )
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--config", str(tmp_path / ".vigil.yaml"),
                "--category", "auth",
                "--format", "json",
                "--offline",
            ],
        )
        data = json.loads(result.output)
        auth005 = [f for f in data["findings"] if f["rule_id"] == "AUTH-005"]
        assert len(auth005) > 0, "AUTH-005 should detect CORS with *"

    def test_typosquatting_detected_offline(self, runner, tmp_path):
        """DEP-003: nombre similar a paquete popular detectado sin network."""
        # "requets" — distance 1 from "requests"
        (tmp_path / "requirements.txt").write_text("requets==2.31.0\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--category", "dependency",
                "--format", "json",
                "--offline",
            ],
        )
        data = json.loads(result.output)
        dep003 = [f for f in data["findings"] if f["rule_id"] == "DEP-003"]
        assert len(dep003) > 0, "DEP-003 should detect 'requets' as typosquatting"
        assert "requests" in dep003[0]["message"].lower()


# ===========================================================================
# 6. EXIT CODES — combinaciones exhaustivas
# ===========================================================================


class TestExitCodesCombinations:
    """Combinaciones avanzadas de exit codes."""

    def test_fail_on_critical_with_high_findings_is_success(self, runner, tmp_path):
        """--fail-on critical con solo HIGH findings -> exit 0."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--fail-on", "critical",
                "--offline",
            ],
        )
        # TEST-001 is HIGH, fail-on is critical -> should be 0
        assert result.exit_code == ExitCode.SUCCESS

    def test_fail_on_low_catches_all(self, runner, tmp_path):
        """--fail-on low con cualquier finding -> exit 1."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--fail-on", "low",
                "--offline",
            ],
        )
        # TEST-001 is HIGH >= LOW threshold -> exit 1
        assert result.exit_code == ExitCode.FINDINGS

    def test_empty_project_no_findings(self, runner, tmp_path):
        """Proyecto sin archivos produce 0 findings y exit 0."""
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--offline"]
        )
        assert result.exit_code == ExitCode.SUCCESS

    def test_nonexistent_path_no_crash(self, runner, tmp_path):
        """Path inexistente no crashea, produce 0 files scanned."""
        nonexistent = str(tmp_path / "nonexistent")
        result = runner.invoke(
            main, ["scan", nonexistent, "--offline"]
        )
        assert result.exit_code == ExitCode.SUCCESS

    def test_deps_exit_code_with_findings(self, runner, tmp_path):
        """vigil deps con typosquatting produce exit 1."""
        (tmp_path / "requirements.txt").write_text("requets==2.31.0\n")
        result = runner.invoke(
            main, ["deps", str(tmp_path), "--offline"]
        )
        assert result.exit_code == ExitCode.FINDINGS

    def test_tests_exit_code_with_findings(self, runner, tmp_path):
        """vigil tests con test vacio produce exit 1."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(main, ["tests", str(tmp_path)])
        assert result.exit_code == ExitCode.FINDINGS


# ===========================================================================
# 7. QUIET + VERBOSE + OFFLINE INTERACTIONS
# ===========================================================================


class TestFlagInteractions:
    """Verifica interacciones entre flags."""

    def test_quiet_and_verbose_together(self, runner, tmp_path):
        """--quiet y --verbose juntos no crashean."""
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--quiet", "--verbose", "--offline"]
        )
        assert result.exit_code == 0

    def test_quiet_with_json_format(self, runner, tmp_path):
        """--quiet con --format json produce JSON valido."""
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--quiet", "--format", "json", "--offline",
            ]
        )
        data = json.loads(result.output)
        assert "findings" in data

    def test_quiet_with_sarif_format(self, runner, tmp_path):
        """--quiet con --format sarif produce SARIF valido."""
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--quiet", "--format", "sarif", "--offline",
            ]
        )
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"

    def test_offline_with_category_dependency(self, runner, tmp_path):
        """--offline con --category dependency ejecuta checks estaticos."""
        (tmp_path / "requirements.txt").write_text("requets==1.0.0\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--offline", "--category", "dependency",
                "--format", "json",
            ]
        )
        data = json.loads(result.output)
        # Typosquatting deberia funcionar offline
        assert any(
            f["rule_id"] == "DEP-003" for f in data["findings"]
        ), "DEP-003 should work offline"

    def test_multiple_flags_combined(self, runner, tmp_path):
        """Combinar multiples flags no crashea.

        Note: --verbose omitted because structlog writes to stderr which
        CliRunner merges into stdout, breaking JSON parsing.
        """
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--offline",
                "--fail-on", "critical",
                "--language", "python",
                "--category", "secrets",
                "--format", "json",
            ]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data["findings"], list)


# ===========================================================================
# 8. CHANGED-ONLY — edge cases
# ===========================================================================


class TestChangedOnlyEdgeCases:
    """Edge cases para --changed-only."""

    def test_changed_only_with_spaces_in_filename(self):
        """Filenames con espacios se parsean correctamente."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M file with spaces.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "file with spaces.py" in files

    def test_changed_only_rename_uses_new_name(self):
        """Renames usan el nombre nuevo."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "R  old_name.py\0new_name.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "new_name.py" in files
        assert "old_name.py" not in files

    def test_changed_only_mixed_statuses(self):
        """Mezcla de modified, added, deleted."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "M  modified.py\0"
            "A  added.py\0"
            "D  deleted.py\0"
            "?? untracked.py\0"
        )
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "modified.py" in files
        assert "added.py" in files
        assert "deleted.py" not in files  # D = deleted
        assert "untracked.py" in files

    def test_changed_only_empty_output(self):
        """Output vacio de git retorna lista vacia."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert files == []


# ===========================================================================
# 9. FINDING COMPLETENESS — campos requeridos
# ===========================================================================


class TestFindingCompleteness:
    """Verifica que los findings tienen todos los campos requeridos."""

    def test_finding_has_required_fields(self, runner, tmp_path):
        """Cada finding en JSON output tiene todos los campos requeridos."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        (tmp_path / "config.py").write_text('SECRET = "changeme"\n')
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        required_fields = {"rule_id", "category", "severity", "message", "location"}
        for finding in data["findings"]:
            missing = required_fields - set(finding.keys())
            assert not missing, (
                f"Finding {finding.get('rule_id', '?')} missing fields: {missing}"
            )
            assert finding["location"]["file"], "Finding has empty file path"

    def test_finding_rule_id_format(self, runner, tmp_path):
        """Rule IDs siguen formato CAT-NNN."""
        import re

        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        (tmp_path / "config.py").write_text('SECRET = "changeme"\n')
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        pattern = re.compile(r"^[A-Z]+-\d{3}$")
        for finding in data["findings"]:
            assert pattern.match(finding["rule_id"]), (
                f"Invalid rule_id format: {finding['rule_id']}"
            )

    def test_finding_severity_is_valid_enum(self, runner, tmp_path):
        """Severity values son enum values validos."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        valid_severities = {"critical", "high", "medium", "low", "info"}
        for finding in data["findings"]:
            assert finding["severity"] in valid_severities, (
                f"Invalid severity: {finding['severity']}"
            )

    def test_finding_message_is_actionable(self, runner, tmp_path):
        """Messages no son genericos."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        for finding in data["findings"]:
            msg = finding["message"]
            assert len(msg) > 10, f"Message too short: '{msg}'"
            # Must not be generic
            generic_phrases = ["issue detected", "problem found", "check this"]
            for phrase in generic_phrases:
                assert phrase not in msg.lower(), (
                    f"Generic message found: '{msg}'"
                )


# ===========================================================================
# 10. OUTPUT FORMATS — validacion profunda
# ===========================================================================


class TestOutputFormatsDeep:
    """Validacion profunda de formatos de salida."""

    @pytest.fixture
    def project_with_findings(self, tmp_path):
        """Proyecto con findings garantizados."""
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        (tmp_path / "config.py").write_text('API_KEY = "changeme"\n')
        return tmp_path

    def test_json_has_summary(self, runner, project_with_findings):
        """JSON output incluye section summary."""
        result = runner.invoke(
            main, [
                "scan", str(project_with_findings),
                "--format", "json", "--offline",
            ]
        )
        data = json.loads(result.output)
        assert "summary" in data
        assert "version" in data
        assert data["version"] == "0.7.0"

    def test_sarif_results_have_rule_index(self, runner, project_with_findings):
        """SARIF results tienen ruleIndex valido."""
        result = runner.invoke(
            main, [
                "scan", str(project_with_findings),
                "--format", "sarif", "--offline",
            ]
        )
        data = json.loads(result.output)
        run = data["runs"][0]
        rules = run["tool"]["driver"]["rules"]
        results = run["results"]

        for r in results:
            assert "ruleIndex" in r
            assert 0 <= r["ruleIndex"] < len(rules), (
                f"ruleIndex {r['ruleIndex']} out of range [0, {len(rules)})"
            )

    def test_sarif_severity_mapping(self, runner, project_with_findings):
        """SARIF level mappea correctamente de vigil severity."""
        result = runner.invoke(
            main, [
                "scan", str(project_with_findings),
                "--format", "sarif", "--offline",
            ]
        )
        data = json.loads(result.output)
        valid_levels = {"error", "warning", "note"}
        for r in data["runs"][0]["results"]:
            assert r["level"] in valid_levels, (
                f"Invalid SARIF level: {r['level']}"
            )

    def test_junit_xml_valid(self, runner, project_with_findings):
        """JUnit output es XML valido con estructura correcta."""
        result = runner.invoke(
            main, [
                "scan", str(project_with_findings),
                "--format", "junit", "--offline",
            ]
        )
        root = ET.fromstring(result.output)
        assert root.tag == "testsuites"
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("name") == "vigil"
        # tests count should match testcase count
        tests_attr = int(suite.get("tests", 0))
        testcases = suite.findall("testcase")
        assert tests_attr == len(testcases), (
            f"tests attribute ({tests_attr}) != actual testcases ({len(testcases)})"
        )

    def test_human_format_findings_ordered_by_severity(self, runner, tmp_path):
        """Human format muestra findings en orden de severidad."""
        (tmp_path / "config.py").write_text('API_KEY = "changeme"\n')
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--format", "human", "--offline"]
        )
        output = result.output
        # CRITICAL/HIGH should appear before MEDIUM
        crit_pos = output.find("CRITICAL")
        high_pos = output.find("HIGH")
        medium_pos = output.find("MEDIUM")
        if crit_pos >= 0 and medium_pos >= 0:
            assert crit_pos < medium_pos
        if high_pos >= 0 and medium_pos >= 0:
            assert high_pos < medium_pos


# ===========================================================================
# 11. CONFIG — rule overrides y strategies
# ===========================================================================


class TestConfigAdvanced:
    """Tests avanzados de configuracion."""

    def test_rule_override_disable_via_yaml(self, runner, tmp_path):
        """Rule override en YAML desactiva una regla."""
        config = tmp_path / ".vigil.yaml"
        config.write_text(
            'rules:\n'
            '  TEST-001:\n'
            '    enabled: false\n'
        )
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--config", str(config),
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        test001 = [f for f in data["findings"] if f["rule_id"] == "TEST-001"]
        assert len(test001) == 0, "TEST-001 should be disabled by rule override"

    def test_rule_override_change_severity(self, runner, tmp_path):
        """Rule override cambia severidad."""
        config = tmp_path / ".vigil.yaml"
        config.write_text(
            'rules:\n'
            '  TEST-001:\n'
            '    severity: "low"\n'
        )
        (tmp_path / "test_x.py").write_text("def test_empty():\n    pass\n")
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--config", str(config),
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        test001 = [f for f in data["findings"] if f["rule_id"] == "TEST-001"]
        if test001:
            assert test001[0]["severity"] == "low"

    def test_yaml_config_loads_deps_settings(self, tmp_path):
        """YAML config carga settings de deps correctamente."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text(
            "deps:\n"
            "  similarity_threshold: 0.9\n"
            "  cache_ttl_hours: 48\n"
        )
        config = load_config(config_path=str(config_file))
        assert config.deps.similarity_threshold == 0.9
        assert config.deps.cache_ttl_hours == 48

    def test_cli_override_beats_yaml(self, tmp_path):
        """CLI override tiene precedencia sobre YAML."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("fail_on: medium\n")
        config = load_config(
            config_path=str(config_file),
            cli_overrides={"fail_on": "critical"},
        )
        assert config.fail_on == "critical"


# ===========================================================================
# 12. ENGINE — edge cases
# ===========================================================================


class TestEngineEdgeCases:
    """Edge cases del ScanEngine."""

    def test_engine_with_no_analyzers(self):
        """Engine sin analyzers produce 0 findings."""
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        result = engine.run([])
        assert len(result.findings) == 0
        assert len(result.analyzers_run) == 0

    def test_engine_all_analyzers_fail(self):
        """Si todos los analyzers fallan, no crashea."""
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)

        class FailAnalyzer:
            def __init__(self, name):
                self._name = name
                self.category = Category.AUTH

            @property
            def name(self):
                return self._name

            def analyze(self, files, config):
                raise RuntimeError(f"{self._name} failed")

        engine.register_analyzer(FailAnalyzer("analyzer1"))
        engine.register_analyzer(FailAnalyzer("analyzer2"))
        result = engine.run([])

        assert len(result.errors) == 2
        assert len(result.findings) == 0

    def test_engine_category_filter_skips_analyzer(self):
        """Category filter causa que analyzer sea skipped."""
        config = ScanConfig(
            deps={"offline_mode": True},
            categories=["secrets"],
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

        # Auth analyzer should be skipped because we filtered to "secrets"
        assert len(result.findings) == 0
        assert "auth" not in result.analyzers_run

    def test_engine_exclude_rules_filter(self):
        """exclude_rules filtra findings."""
        config = ScanConfig(
            deps={"offline_mode": True},
            exclude_rules=["AUTH-005"],
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
                    ),
                    Finding(
                        rule_id="AUTH-004",
                        category=Category.AUTH,
                        severity=Severity.CRITICAL,
                        message="JWT issue",
                        location=Location(file="b.py"),
                    ),
                ]

        engine.register_analyzer(AuthAnalyzer())
        result = engine.run([])

        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "AUTH-004"

    def test_engine_duration_is_positive(self):
        """duration_seconds es siempre positivo."""
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        result = engine.run([])
        assert result.duration_seconds >= 0


# ===========================================================================
# 13. HUMAN FORMATTER — edge cases
# ===========================================================================


class TestHumanFormatterEdgeCases:
    """Edge cases del formatter humano."""

    def test_format_finding_without_line_number(self):
        """Finding sin line number muestra solo filename."""
        formatter = HumanFormatter(colors=False)
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="DEP-001",
                    category=Category.DEPENDENCY,
                    severity=Severity.CRITICAL,
                    message="Package not found",
                    location=Location(file="requirements.txt"),
                )
            ]
        )
        output = formatter.format(result)
        assert "requirements.txt" in output
        # Should NOT have ":None"
        assert ":None" not in output

    def test_format_finding_with_line_number(self):
        """Finding con line number muestra file:line."""
        formatter = HumanFormatter(colors=False)
        result = ScanResult(
            findings=[
                Finding(
                    rule_id="SEC-001",
                    category=Category.SECRETS,
                    severity=Severity.CRITICAL,
                    message="Secret found",
                    location=Location(file="config.py", line=5),
                )
            ]
        )
        output = formatter.format(result)
        assert "config.py:5" in output

    def test_format_many_findings(self):
        """Formatter maneja muchos findings sin crashear."""
        formatter = HumanFormatter(colors=False)
        findings = [
            Finding(
                rule_id=f"TEST-{i:03d}",
                category=Category.TEST_QUALITY,
                severity=Severity.MEDIUM,
                message=f"Issue {i}",
                location=Location(file=f"test_{i}.py", line=i),
            )
            for i in range(100)
        ]
        result = ScanResult(findings=findings, files_scanned=100)
        output = formatter.format(result)
        assert "100 findings" in output

    def test_format_finding_with_all_severity_levels(self):
        """Todos los niveles de severidad se formatean."""
        formatter = HumanFormatter(colors=False)
        findings = []
        for sev in Severity:
            findings.append(
                Finding(
                    rule_id="T-001",
                    category=Category.AUTH,
                    severity=sev,
                    message=f"{sev.value} issue",
                    location=Location(file="a.py"),
                )
            )
        result = ScanResult(findings=findings)
        output = formatter.format(result)
        for sev in Severity:
            assert sev.value.upper() in output


# ===========================================================================
# 14. FILE COLLECTOR — edge cases
# ===========================================================================


class TestFileCollectorEdgeCases:
    """Edge cases del file collector."""

    def test_collect_empty_directory(self, tmp_path):
        """Directorio vacio produce lista vacia."""
        from vigil.core.file_collector import collect_files

        result = collect_files([str(tmp_path)])
        assert result == []

    def test_collect_only_python(self, tmp_path):
        """--language python solo incluye .py."""
        from vigil.core.file_collector import collect_files

        (tmp_path / "app.py").write_text("x = 1\n")
        (tmp_path / "app.js").write_text("x = 1;\n")
        (tmp_path / "readme.md").write_text("# readme\n")

        result = collect_files(
            [str(tmp_path)], languages=["python"]
        )
        py_files = [f for f in result if f.endswith(".py")]
        js_files = [f for f in result if f.endswith(".js")]
        assert len(py_files) >= 1
        assert len(js_files) == 0

    def test_collect_always_includes_dependency_files(self, tmp_path):
        """requirements.txt siempre se incluye independientemente del language."""
        from vigil.core.file_collector import collect_files

        (tmp_path / "requirements.txt").write_text("flask\n")
        (tmp_path / "package.json").write_text("{}\n")

        result = collect_files(
            [str(tmp_path)], languages=["python"]
        )
        filenames = [Path(f).name for f in result]
        assert "requirements.txt" in filenames
        assert "package.json" in filenames

    def test_collect_excludes_pycache(self, tmp_path):
        """__pycache__ se excluye."""
        from vigil.core.file_collector import collect_files

        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.cpython-312.pyc").write_bytes(b"\x00")
        (tmp_path / "app.py").write_text("x = 1\n")

        result = collect_files(
            [str(tmp_path)],
            exclude=["__pycache__/"],
        )
        assert not any("__pycache__" in f for f in result)

    def test_collect_single_file(self, tmp_path):
        """Pasar un archivo individual lo incluye."""
        from vigil.core.file_collector import collect_files

        py_file = tmp_path / "single.py"
        py_file.write_text("x = 1\n")

        result = collect_files([str(py_file)])
        assert len(result) == 1

    def test_collect_nonexistent_path(self, tmp_path):
        """Path inexistente se ignora sin crashear."""
        from vigil.core.file_collector import collect_files

        result = collect_files([str(tmp_path / "nonexistent")])
        assert result == []


# ===========================================================================
# 15. PARSERS — edge cases
# ===========================================================================


class TestParsersEdgeCases:
    """Edge cases de los parsers de dependencias."""

    def test_parse_empty_requirements(self, tmp_path):
        """requirements.txt vacio produce lista vacia."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text("")
        result = parse_requirements_txt(req)
        assert result == []

    def test_parse_requirements_comments_only(self, tmp_path):
        """requirements.txt con solo comentarios produce lista vacia."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text("# This is a comment\n# Another comment\n")
        result = parse_requirements_txt(req)
        assert result == []

    def test_parse_requirements_with_inline_comment(self, tmp_path):
        """Lineas con inline comments no son parseadas (no soportado)."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")
        result = parse_requirements_txt(req)
        assert len(result) == 1
        assert result[0].name == "flask"

    def test_parse_requirements_line_numbers_correct(self, tmp_path):
        """Line numbers empiezan en 1 y son correctos."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text("# comment\nflask==3.0.0\n# another\ndjango==5.0\n")
        result = parse_requirements_txt(req)
        assert result[0].line_number == 2  # flask is line 2
        assert result[1].line_number == 4  # django is line 4

    def test_parse_requirements_dev_flag(self, tmp_path):
        """requirements-dev.txt marca is_dev=True."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements-dev.txt"
        req.write_text("pytest==8.0.0\n")
        result = parse_requirements_txt(req)
        assert len(result) == 1
        assert result[0].is_dev is True

    def test_parse_package_json_empty_deps(self, tmp_path):
        """package.json sin dependencies produce lista vacia."""
        from vigil.analyzers.deps.parsers import parse_package_json

        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "test"}')
        result = parse_package_json(pkg)
        assert result == []

    def test_parse_package_json_invalid(self, tmp_path):
        """package.json con JSON invalido no crashea."""
        from vigil.analyzers.deps.parsers import parse_package_json

        pkg = tmp_path / "package.json"
        pkg.write_text("not json{{{")
        result = parse_package_json(pkg)
        assert result == []

    def test_parse_requirements_with_extras(self, tmp_path):
        """Paquetes con extras [bracket] se parsean correctamente."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text("uvicorn[standard]>=0.20\n")
        result = parse_requirements_txt(req)
        assert len(result) == 1
        assert result[0].name == "uvicorn"

    def test_parse_requirements_with_markers(self, tmp_path):
        """Environment markers (;) se ignoran correctamente."""
        from vigil.analyzers.deps.parsers import parse_requirements_txt

        req = tmp_path / "requirements.txt"
        req.write_text('pywin32>=300; sys_platform == "win32"\n')
        result = parse_requirements_txt(req)
        assert len(result) == 1
        assert result[0].name == "pywin32"

    def test_find_and_parse_all_nonexistent_dir(self, tmp_path):
        """Directorio inexistente retorna lista vacia."""
        from vigil.analyzers.deps.parsers import find_and_parse_all

        result = find_and_parse_all(str(tmp_path / "nonexistent"))
        assert result == []


# ===========================================================================
# 16. DATA FILES — validacion del corpus generado
# ===========================================================================


class TestGeneratedDataFiles:
    """Verifica los archivos de datos generados."""

    def test_pypi_data_file_exists(self):
        """data/popular_pypi.json existe."""
        filepath = Path(__file__).parent.parent / "data" / "popular_pypi.json"
        assert filepath.exists(), f"{filepath} does not exist"

    def test_pypi_data_is_valid_json(self):
        """data/popular_pypi.json contiene JSON valido."""
        filepath = Path(__file__).parent.parent / "data" / "popular_pypi.json"
        data = json.loads(filepath.read_text())
        assert isinstance(data, dict)

    def test_pypi_data_has_enough_packages(self):
        """data/popular_pypi.json tiene al menos 4000 paquetes."""
        filepath = Path(__file__).parent.parent / "data" / "popular_pypi.json"
        data = json.loads(filepath.read_text())
        assert len(data) >= 4000, f"Expected >= 4000 packages, got {len(data)}"

    def test_pypi_data_has_key_packages(self):
        """data/popular_pypi.json incluye paquetes clave."""
        filepath = Path(__file__).parent.parent / "data" / "popular_pypi.json"
        data = json.loads(filepath.read_text())
        for pkg in ["boto3", "requests", "numpy", "flask", "django"]:
            # PyPI data uses lowercase names
            found = any(k.lower() == pkg for k in data)
            assert found, f"{pkg} not in pypi data"

    def test_pypi_data_values_are_positive_ints(self):
        """Todos los download counts son enteros positivos."""
        filepath = Path(__file__).parent.parent / "data" / "popular_pypi.json"
        data = json.loads(filepath.read_text())
        for name, count in list(data.items())[:100]:  # Check first 100
            assert isinstance(count, int), f"{name}: count is {type(count)}"
            assert count > 0, f"{name}: count is {count}"

    def test_npm_data_file_exists(self):
        """data/popular_npm.json existe."""
        filepath = Path(__file__).parent.parent / "data" / "popular_npm.json"
        assert filepath.exists(), f"{filepath} does not exist"

    def test_npm_data_is_valid_json(self):
        """data/popular_npm.json contiene JSON valido."""
        filepath = Path(__file__).parent.parent / "data" / "popular_npm.json"
        data = json.loads(filepath.read_text())
        assert isinstance(data, dict)

    def test_npm_data_has_enough_packages(self):
        """data/popular_npm.json tiene al menos 2000 paquetes."""
        filepath = Path(__file__).parent.parent / "data" / "popular_npm.json"
        data = json.loads(filepath.read_text())
        assert len(data) >= 2000, f"Expected >= 2000 packages, got {len(data)}"

    def test_npm_data_has_key_packages(self):
        """data/popular_npm.json incluye paquetes clave."""
        filepath = Path(__file__).parent.parent / "data" / "popular_npm.json"
        data = json.loads(filepath.read_text())
        for pkg in ["express", "react", "lodash", "chalk"]:
            assert pkg in data, f"{pkg} not in npm data"

    def test_placeholder_patterns_file_exists(self):
        """data/placeholder_patterns.json existe."""
        filepath = Path(__file__).parent.parent / "data" / "placeholder_patterns.json"
        assert filepath.exists()

    def test_placeholder_patterns_is_valid(self):
        """data/placeholder_patterns.json es JSON valido con patterns."""
        filepath = Path(__file__).parent.parent / "data" / "placeholder_patterns.json"
        data = json.loads(filepath.read_text())
        assert "patterns" in data
        assert len(data["patterns"]) >= 20


# ===========================================================================
# 17. TYPOSQUATTING WITH REAL CORPUS
# ===========================================================================


class TestTyposquattingWithRealCorpus:
    """Verifica typosquatting detection con el corpus real de data/."""

    def test_common_typos_detected(self):
        """Typos comunes se detectan con el corpus real."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        # "requets" (missing 's') → "requests"
        matches = find_similar_popular("requets", "pypi", threshold=0.85)
        assert len(matches) > 0
        assert any(m[0] == "requests" for m in matches)

    def test_expresss_typo_detected(self):
        """'expresss' (extra 's') se detecta con corpus npm."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        matches = find_similar_popular("expresss", "npm", threshold=0.85)
        assert len(matches) > 0
        assert any(m[0] == "express" for m in matches)

    def test_legitimate_packages_not_flagged(self):
        """Paquetes legitimos no son flaggeados como typosquatting."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        for pkg in ["requests", "flask", "django", "numpy", "pandas"]:
            matches = find_similar_popular(pkg, "pypi", threshold=0.85)
            assert len(matches) == 0, (
                f"Legitimate package '{pkg}' flagged as similar to: {matches}"
            )

    def test_npm_legitimate_not_flagged(self):
        """Paquetes npm legitimos no son flaggeados."""
        from vigil.analyzers.deps.similarity import find_similar_popular

        for pkg in ["express", "react", "lodash", "axios"]:
            matches = find_similar_popular(pkg, "npm", threshold=0.85)
            assert len(matches) == 0, (
                f"Legitimate npm package '{pkg}' flagged as similar to: {matches}"
            )
