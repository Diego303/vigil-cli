"""QA regression tests para FASE 5.

Cubre:
- Bugs encontrados en audit
- Edge cases (archivos vacios, unicode, BOM, encoding)
- Falsos positivos (codigo limpio NO debe generar findings)
- Falsos negativos (codigo inseguro DEBE generar findings especificos)
- CLI edge cases
- Configuracion
- Integracion engine + overrides
- Regresiones para cada bug del audit
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from vigil.cli import ExitCode, _get_changed_files, main
from vigil.config.loader import (
    _merge_cli_overrides,
    find_config_file,
    generate_config_yaml,
    load_config,
)
from vigil.config.schema import RuleOverride, ScanConfig
from vigil.core.engine import ScanEngine, ScanResult
from vigil.core.file_collector import collect_files
from vigil.core.finding import Category, Finding, Location, Severity

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "integration"
INSECURE_DIR = FIXTURES_DIR / "insecure_project"
CLEAN_DIR = FIXTURES_DIR / "clean_project"


@pytest.fixture
def runner():
    return CliRunner()


# ===========================================================================
# 1. REGRESSION TESTS — bugs encontrados en audit
# ===========================================================================


class TestRegressionGetChangedFiles:
    """Regresiones para _get_changed_files() — audit bug en cli.py:375."""

    def test_deletion_both_fields_D(self):
        """status='DD' debe excluir el archivo (ambos campos D)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "DD deleted.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "deleted.py" not in files

    def test_deletion_only_index_D(self):
        """status='D ' (staged delete) debe excluir."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "D  staged_del.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "staged_del.py" not in files

    def test_deletion_only_worktree_D(self):
        """status=' D' (unstaged delete) debe excluir."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " D worktree_del.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "worktree_del.py" not in files

    def test_modified_D_in_filename_included(self):
        """Un archivo con 'D' en el nombre pero status ' M' debe incluirse."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M Django_app.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "Django_app.py" in files

    def test_entry_too_short_no_crash(self):
        """Un entry con menos de 3 caracteres no debe crashear."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # Simular un entry corrupto de 2 chars
        mock_result.stdout = "??\0 M ok.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        # No debe crashear; ok.py puede o no incluirse dependiendo del parsing
        assert isinstance(files, list)

    def test_entry_exactly_3_chars(self):
        """Un entry de exactamente 3 chars tiene filename vacio."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # "?? " has filename = "" (entry[3:] = "")
        mock_result.stdout = "?? \0 M real.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "real.py" in files

    def test_rename_with_deletion_excluded(self):
        """Rename donde el status indica D no debe incluir."""
        # This is a weird edge case — R status typically doesn't have D
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "R  old.py\0new.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "new.py" in files
        assert "old.py" not in files

    def test_copy_status_uses_new_name(self):
        """Copy (C) status debe usar el nombre nuevo."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "C  original.py\0copy.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "copy.py" in files

    def test_multiple_renames_interleaved(self):
        """Multiples renames en secuencia se parsean correctamente."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "R  a.py\0b.py\0R  c.py\0d.py\0 M e.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        assert "b.py" in files
        assert "d.py" in files
        assert "e.py" in files
        assert "a.py" not in files
        assert "c.py" not in files

    def test_rename_at_end_of_output_missing_target(self):
        """Rename al final sin target entry no debe crashear."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # Rename sin segundo campo (output truncado)
        mock_result.stdout = "R  old.py\0"
        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()
        # No debe crashear — puede incluir o no old.py
        assert isinstance(files, list)


class TestRegressionEngineIncludeField:
    """Regresion: include config field existe pero nunca se usa en _collect_files.
    engine.py:120-126 pasa exclude y languages pero no include.
    """

    def test_include_field_not_passed_to_collector(self):
        """Documenta que include se ignora — el engine no lo pasa a collect_files."""
        config = ScanConfig(include=["src/", "lib/"])
        engine = ScanEngine(config)
        # El _collect_files no pasa include — verificar via mock
        with patch("vigil.core.engine.collect_files", return_value=[]) as mock_collect:
            engine._collect_files(["some_path"])
            _, kwargs = mock_collect.call_args
            # include no aparece en los kwargs
            assert "include" not in kwargs


class TestRegressionLoaderYamlValidation:
    """Regresion: loader.py no valida que YAML sea dict."""

    def test_yaml_with_list_content(self, tmp_path):
        """YAML que contiene una lista en vez de dict no crashea."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("- item1\n- item2\n")
        # yaml.safe_load returns a list, which would fail at ScanConfig(**merged)
        # but should it fail gracefully?
        with pytest.raises(Exception):
            load_config(config_path=str(config_file))

    def test_yaml_with_string_content(self, tmp_path):
        """YAML que contiene un string no crashea."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("just a string\n")
        with pytest.raises(Exception):
            load_config(config_path=str(config_file))

    def test_yaml_with_integer_content(self, tmp_path):
        """YAML que contiene un entero no crashea."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("42\n")
        with pytest.raises(Exception):
            load_config(config_path=str(config_file))

    def test_yaml_empty_file(self, tmp_path):
        """YAML vacio retorna config con defaults."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("")
        config = load_config(config_path=str(config_file))
        assert config.fail_on == "high"

    def test_yaml_null_value(self, tmp_path):
        """YAML con solo 'null' retorna config con defaults."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text("null\n")
        config = load_config(config_path=str(config_file))
        assert config.fail_on == "high"

    def test_valid_yaml_loads_correctly(self, tmp_path):
        """YAML valido carga correctamente."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text('fail_on: "critical"\n')
        config = load_config(config_path=str(config_file))
        assert config.fail_on == "critical"


class TestRegressionCleanProjectFindings:
    """Regresion: test_scan_clean_no_findings solo verifica exit code,
    no verifica que el count sea 0 — audit finding en test_integration_e2e.py:325.
    """

    def test_clean_project_zero_critical_high_findings(self):
        """El proyecto limpio debe tener 0 findings CRITICAL/HIGH (excepto AUTH-002 en /login).

        AUTH-002 en POST /login es un known behavior — login endpoints
        no tienen auth middleware por diseño. Usuarios pueden desactivar con override.
        """
        from vigil.cli import _register_analyzers

        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(CLEAN_DIR)])

        critical_high = [
            f for f in result.findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
            and not (f.rule_id == "AUTH-002" and "/login" in f.message)
        ]
        assert len(critical_high) == 0, (
            f"Clean project has {len(critical_high)} CRITICAL/HIGH findings: "
            f"{[(f.rule_id, f.message) for f in critical_high]}"
        )

    def test_clean_project_no_secret_findings_at_all(self):
        """El proyecto limpio no debe tener findings de SEC-*."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(CLEAN_DIR)])

        sec_findings = [f for f in result.findings if f.rule_id.startswith("SEC-")]
        assert len(sec_findings) == 0, (
            f"Clean project has SEC findings: "
            f"{[(f.rule_id, f.message) for f in sec_findings]}"
        )


class TestRegressionEngineShouldRun:
    """Regresion: engine.py:133-136 _should_run() tiene rules_filter incompleto.
    El filtro de reglas tiene un 'pass' en vez de logica real.
    """

    def test_rules_filter_does_not_skip_analyzers(self):
        """Con rules_filter, todos los analyzers corren (filtro es post-hoc)."""
        config = ScanConfig(
            deps={"offline_mode": True},
            rules_filter=["AUTH-005"],
        )
        engine = ScanEngine(config)

        class FakeAnalyzer:
            name = "fake"
            category = Category.AUTH

            def analyze(self, files, config):
                return []

        engine.register_analyzer(FakeAnalyzer())
        # _should_run no filtra por rules_filter (pass statement)
        assert engine._should_run(FakeAnalyzer()) is True

    def test_rules_filter_applies_in_apply_overrides(self):
        """rules_filter filtra findings en _apply_rule_overrides, no en _should_run."""
        config = ScanConfig(rules_filter=["AUTH-005"])
        engine = ScanEngine(config)

        result = ScanResult(findings=[
            Finding(
                rule_id="AUTH-005",
                category=Category.AUTH,
                severity=Severity.HIGH,
                message="CORS wildcard",
                location=Location(file="app.py", line=1),
            ),
            Finding(
                rule_id="AUTH-001",
                category=Category.AUTH,
                severity=Severity.HIGH,
                message="No auth",
                location=Location(file="app.py", line=2),
            ),
        ])
        engine._apply_rule_overrides(result)
        # Solo AUTH-005 debe quedar
        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "AUTH-005"


# ===========================================================================
# 2. EDGE CASE TESTS
# ===========================================================================


class TestEdgeCaseEmptyProject:
    """Edge cases con proyectos vacios o sin archivos."""

    def test_scan_empty_directory(self, tmp_path):
        """Scan de directorio vacio retorna 0 findings."""
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])
        assert result.findings == []
        assert result.files_scanned == 0
        assert len(result.errors) == 0

    def test_scan_empty_file(self, tmp_path):
        """Archivo .py vacio no genera findings ni errores."""
        (tmp_path / "empty.py").write_text("")
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])
        assert len(result.errors) == 0

    def test_scan_whitespace_only_file(self, tmp_path):
        """Archivo con solo whitespace no genera errores."""
        (tmp_path / "spaces.py").write_text("   \n\n   \n")
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])
        assert len(result.errors) == 0


class TestEdgeCaseEncoding:
    """Edge cases de encoding — BOM, Latin-1, etc."""

    def test_utf8_bom_file(self, tmp_path):
        """Archivo con UTF-8 BOM no crashea el scan."""
        content = '\ufeff# -*- coding: utf-8 -*-\nx = 1\n'
        (tmp_path / "bom.py").write_text(content, encoding="utf-8-sig")
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])
        assert len(result.errors) == 0

    def test_latin1_file(self, tmp_path):
        """Archivo con encoding Latin-1 no crashea (uses errors='replace')."""
        content = b"# Caf\xe9 script\nx = 1\n"
        (tmp_path / "latin.py").write_bytes(content)
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])
        assert len(result.errors) == 0

    def test_binary_file_extension_skipped(self, tmp_path):
        """Archivos binarios con extension no-Python no se escanean."""
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        result = engine.run([str(tmp_path)])
        assert len(result.errors) == 0


class TestEdgeCaseFilenames:
    """Edge cases de nombres de archivos."""

    def test_filename_with_spaces(self, tmp_path):
        """Archivo con espacios en el nombre se escanea."""
        (tmp_path / "my file.py").write_text("x = 1")
        files = collect_files([str(tmp_path)])
        assert any("my file.py" in f for f in files)

    def test_deep_nested_file(self, tmp_path):
        """Archivo en directorio profundamente anidado se encuentra."""
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("x = 1")
        files = collect_files([str(tmp_path)])
        assert any("deep.py" in f for f in files)

    def test_nonexistent_path(self):
        """Path inexistente no crashea collect_files."""
        files = collect_files(["/nonexistent/path/abc123"])
        assert files == []


class TestEdgeCaseFileCollector:
    """Edge cases del file collector."""

    def test_single_file_path(self, tmp_path):
        """Pasar un archivo individual funciona."""
        f = tmp_path / "single.py"
        f.write_text("x = 1")
        files = collect_files([str(f)])
        assert len(files) == 1

    def test_duplicate_paths(self, tmp_path):
        """Paths duplicados se deduplicane."""
        (tmp_path / "app.py").write_text("x = 1")
        path = str(tmp_path)
        files = collect_files([path, path])
        # Debe deduplicar
        py_files = [f for f in files if f.endswith("app.py")]
        assert len(py_files) == 1

    def test_exclude_pattern(self, tmp_path):
        """Exclude patterns filtran directorios correctamente."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("x = 1")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("x = 1")
        files = collect_files(
            [str(tmp_path)],
            exclude=["node_modules"],
        )
        assert not any("node_modules" in f for f in files)
        assert any("app.py" in f for f in files)

    def test_language_filter_python_only(self, tmp_path):
        """Filtro de lenguaje solo incluye archivos Python."""
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "server.js").write_text("x = 1")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any("app.py" in f for f in files)
        assert not any("server.js" in f for f in files)

    def test_dependency_files_always_included(self, tmp_path):
        """requirements.txt se incluye incluso con filtro de lenguaje JS."""
        (tmp_path / "requirements.txt").write_text("flask==3.0")
        (tmp_path / "app.py").write_text("x = 1")
        files = collect_files([str(tmp_path)], languages=["javascript"])
        assert any("requirements.txt" in f for f in files)


# ===========================================================================
# 3. FALSE POSITIVE TESTS (codigo limpio NO debe generar findings)
# ===========================================================================


class TestFalsePositivesAuth:
    """Codigo de auth bien escrito no debe generar findings."""

    def test_cors_with_specific_origins(self, tmp_path):
        """CORS con origenes especificos no debe generar AUTH-005."""
        code = '''
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])
'''
        (tmp_path / "app.py").write_text(code)
        findings = self._scan_auth(tmp_path)
        assert not any(f.rule_id == "AUTH-005" for f in findings)

    def test_env_var_secret(self, tmp_path):
        """Secret leido de env var no debe generar AUTH-004."""
        code = '''
import os
SECRET_KEY = os.environ["JWT_SECRET"]
'''
        (tmp_path / "app.py").write_text(code)
        findings = self._scan_auth(tmp_path)
        assert not any(f.rule_id == "AUTH-004" for f in findings)

    def test_protected_delete_endpoint(self, tmp_path):
        """DELETE con Depends(auth) no debe generar AUTH-002."""
        code = '''
from fastapi import Depends, FastAPI

app = FastAPI()

@app.delete("/items/{id}", dependencies=[Depends(get_current_user)])
async def delete_item(id: int):
    return {"deleted": id}
'''
        (tmp_path / "app.py").write_text(code)
        findings = self._scan_auth(tmp_path)
        assert not any(f.rule_id == "AUTH-002" for f in findings)

    def _scan_auth(self, path):
        from vigil.analyzers.auth import AuthAnalyzer
        analyzer = AuthAnalyzer()
        files = collect_files([str(path)])
        return analyzer.analyze(files, ScanConfig())


class TestFalsePositivesSecrets:
    """Codigo sin secretos no debe generar findings."""

    def test_env_var_read(self, tmp_path):
        """os.environ[KEY] sin default no debe generar SEC-004."""
        code = 'import os\nDB_PASSWORD = os.environ["DB_PASSWORD"]\n'
        (tmp_path / "app.py").write_text(code)
        findings = self._scan_secrets(tmp_path)
        assert not any(f.rule_id == "SEC-004" for f in findings)

    def test_high_entropy_constant(self, tmp_path):
        """Constante con alta entropia que NO es secret no debe generar SEC-002."""
        code = 'HASH_ALGORITHM = "sha256"\n'
        (tmp_path / "app.py").write_text(code)
        findings = self._scan_secrets(tmp_path)
        sec002 = [f for f in findings if f.rule_id == "SEC-002"]
        # sha256 tiene alta entropia pero no es una asignacion de secret
        assert len(sec002) == 0

    def _scan_secrets(self, path):
        from vigil.analyzers.secrets import SecretsAnalyzer
        analyzer = SecretsAnalyzer()
        files = collect_files([str(path)])
        return analyzer.analyze(files, ScanConfig())


class TestFalsePositivesTestQuality:
    """Tests bien escritos no deben generar findings."""

    def test_well_written_tests(self, tmp_path):
        """Tests con assertions reales no generan TEST-001."""
        code = '''
def test_addition():
    assert 1 + 1 == 2

def test_string_operations():
    result = "hello".upper()
    assert result == "HELLO"
    assert len(result) == 5
'''
        (tmp_path / "test_math.py").write_text(code)
        findings = self._scan_tests(tmp_path)
        assert not any(f.rule_id == "TEST-001" for f in findings)
        assert not any(f.rule_id == "TEST-002" for f in findings)

    def test_skip_with_reason(self, tmp_path):
        """Test con skip + reason no genera TEST-004."""
        code = '''
import pytest

@pytest.mark.skip(reason="Requires external API")
def test_external_api():
    result = call_api()
    assert result.status == 200
'''
        (tmp_path / "test_skip.py").write_text(code)
        findings = self._scan_tests(tmp_path)
        assert not any(f.rule_id == "TEST-004" for f in findings)

    def test_proper_exception_test(self, tmp_path):
        """Test con pytest.raises() no genera TEST-003."""
        code = '''
import pytest

def test_raises_value_error():
    with pytest.raises(ValueError):
        int("not-a-number")
'''
        (tmp_path / "test_exc.py").write_text(code)
        findings = self._scan_tests(tmp_path)
        assert not any(f.rule_id == "TEST-003" for f in findings)

    def _scan_tests(self, path):
        from vigil.analyzers.tests import TestQualityAnalyzer
        analyzer = TestQualityAnalyzer()
        files = collect_files([str(path)])
        return analyzer.analyze(files, ScanConfig())


# ===========================================================================
# 4. FALSE NEGATIVE TESTS (codigo inseguro DEBE generar findings)
# ===========================================================================


class TestFalseNegativesAuth:
    """Auth issues DEBEN ser detectados."""

    def test_cors_wildcard_detected(self, tmp_path):
        """CORS con '*' DEBE generar AUTH-005.

        Nota: cors_allow_localhost=True (default) suprime AUTH-005 en paths
        con 'test'/'dev'/'local'/'example'. Usamos cors_allow_localhost=False
        para probar deteccion pura.
        """
        code = '''
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])
'''
        (tmp_path / "app.py").write_text(code)
        from vigil.analyzers.auth import AuthAnalyzer
        analyzer = AuthAnalyzer()
        files = collect_files([str(tmp_path)])
        config = ScanConfig(auth={"cors_allow_localhost": False})
        findings = analyzer.analyze(files, config)
        assert any(f.rule_id == "AUTH-005" for f in findings), \
            "AUTH-005 should detect CORS wildcard"

    def test_hardcoded_jwt_secret_detected(self, tmp_path):
        """JWT secret hardcoded DEBE generar AUTH-004."""
        code = '''
SECRET_KEY = "mysecretkey123"
'''
        (tmp_path / "app.py").write_text(code)
        from vigil.analyzers.auth import AuthAnalyzer
        analyzer = AuthAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "AUTH-004" for f in findings), \
            "AUTH-004 should detect hardcoded JWT secret"

    def test_unprotected_delete_detected(self, tmp_path):
        """DELETE sin auth DEBE generar AUTH-002."""
        code = '''
from fastapi import FastAPI
app = FastAPI()

@app.delete("/users/{id}")
async def delete_user(id: int):
    return {"deleted": id}
'''
        (tmp_path / "app.py").write_text(code)
        from vigil.analyzers.auth import AuthAnalyzer
        analyzer = AuthAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "AUTH-002" for f in findings), \
            "AUTH-002 should detect unprotected DELETE"


class TestFalseNegativesSecrets:
    """Secret issues DEBEN ser detectados."""

    def test_placeholder_secret_detected(self, tmp_path):
        """Placeholder 'your-api-key-here' DEBE generar SEC-001."""
        code = 'API_KEY = "your-api-key-here"\n'
        (tmp_path / "config.py").write_text(code)
        from vigil.analyzers.secrets import SecretsAnalyzer
        analyzer = SecretsAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "SEC-001" for f in findings), \
            "SEC-001 should detect placeholder secrets"

    def test_connection_string_detected(self, tmp_path):
        """Connection string con password DEBE generar SEC-003."""
        code = 'DB_URL = "postgresql://admin:password123@db.example.com:5432/app"\n'
        (tmp_path / "config.py").write_text(code)
        from vigil.analyzers.secrets import SecretsAnalyzer
        analyzer = SecretsAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "SEC-003" for f in findings), \
            "SEC-003 should detect connection string with credentials"

    def test_env_with_default_detected(self, tmp_path):
        """os.environ.get con default hardcoded DEBE generar SEC-004."""
        code = '''
import os
API_KEY = os.environ.get("API_KEY", "hardcoded-default-key")
'''
        (tmp_path / "app.py").write_text(code)
        from vigil.analyzers.secrets import SecretsAnalyzer
        analyzer = SecretsAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "SEC-004" for f in findings), \
            "SEC-004 should detect env var with hardcoded default"


class TestFalseNegativesTestQuality:
    """Test quality issues DEBEN ser detectados."""

    def test_empty_test_detected(self, tmp_path):
        """Test sin assertions DEBE generar TEST-001."""
        code = '''
def test_login():
    response = client.post("/login")
'''
        (tmp_path / "test_app.py").write_text(code)
        from vigil.analyzers.tests import TestQualityAnalyzer
        analyzer = TestQualityAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "TEST-001" for f in findings), \
            "TEST-001 should detect test without assertions"

    def test_trivial_assertion_detected(self, tmp_path):
        """assert x is not None DEBE generar TEST-002."""
        code = '''
def test_user():
    user = get_user(1)
    assert user is not None
'''
        (tmp_path / "test_user.py").write_text(code)
        from vigil.analyzers.tests import TestQualityAnalyzer
        analyzer = TestQualityAnalyzer()
        files = collect_files([str(tmp_path)])
        findings = analyzer.analyze(files, ScanConfig())
        assert any(f.rule_id == "TEST-002" for f in findings), \
            "TEST-002 should detect trivial assertions"


# ===========================================================================
# 5. CLI EDGE CASE TESTS
# ===========================================================================


class TestCLIEdgeCases:
    """Edge cases del CLI."""

    def test_scan_nonexistent_path(self, runner):
        """Scan de path inexistente no crashea."""
        result = runner.invoke(main, ["scan", "/nonexistent/path/xyz", "--offline"])
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.ERROR)

    def test_scan_multiple_paths(self, runner, tmp_path):
        """Scan con multiples paths funciona."""
        d1 = tmp_path / "dir1"
        d1.mkdir()
        (d1 / "a.py").write_text("x = 1")
        d2 = tmp_path / "dir2"
        d2.mkdir()
        (d2 / "b.py").write_text("y = 2")
        result = runner.invoke(main, ["scan", str(d1), str(d2), "--offline"])
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_output_to_nested_directory(self, runner, tmp_path):
        """--output a directorio inexistente crea los padres."""
        output_file = tmp_path / "reports" / "sub" / "report.json"
        result = runner.invoke(main, [
            "scan", str(tmp_path),
            "--format", "json",
            "--output", str(output_file),
            "--offline",
        ])
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)
        assert output_file.exists()

    def test_init_nonexistent_directory(self, runner):
        """init en directorio inexistente falla con ERROR."""
        result = runner.invoke(main, ["init", "/nonexistent/abc"])
        assert result.exit_code == ExitCode.ERROR

    def test_init_no_overwrite_without_force(self, runner, tmp_path):
        """init no sobreescribe sin --force."""
        (tmp_path / ".vigil.yaml").write_text("fail_on: critical\n")
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == ExitCode.ERROR
        assert "already exists" in result.output

    def test_init_overwrites_with_force(self, runner, tmp_path):
        """init sobreescribe con --force."""
        (tmp_path / ".vigil.yaml").write_text("fail_on: critical\n")
        result = runner.invoke(main, ["init", "--force", str(tmp_path)])
        assert result.exit_code == 0

    def test_rules_command(self, runner):
        """vigil rules lista reglas sin crashear."""
        result = runner.invoke(main, ["rules"])
        assert result.exit_code == 0
        assert "DEP-001" in result.output
        assert "AUTH-001" in result.output
        assert "SEC-001" in result.output
        assert "TEST-001" in result.output

    def test_version_command(self, runner):
        """--version muestra version."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "vigil" in result.output

    def test_help_command(self, runner):
        """--help muestra ayuda."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "scan" in result.output

    def test_scan_help(self, runner):
        """scan --help muestra opciones de scan."""
        result = runner.invoke(main, ["scan", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--changed-only" in result.output

    def test_invalid_format(self, runner, tmp_path):
        """Formato invalido genera error."""
        result = runner.invoke(main, [
            "scan", str(tmp_path), "--format", "invalid"
        ])
        assert result.exit_code != 0

    def test_invalid_fail_on(self, runner, tmp_path):
        """fail-on invalido genera error."""
        result = runner.invoke(main, [
            "scan", str(tmp_path), "--fail-on", "invalid"
        ])
        assert result.exit_code != 0


class TestCLIChangedOnlyEdgeCases:
    """Edge cases de --changed-only via CLI."""

    def test_changed_only_with_insecure_files(self, runner):
        """--changed-only con archivos inseguros los detecta."""
        files = [
            str(INSECURE_DIR / "app.py"),
            str(INSECURE_DIR / "config.py"),
        ]
        with patch("vigil.cli._get_changed_files", return_value=files):
            result = runner.invoke(
                main, ["scan", "--changed-only", "--format", "json", "--offline"]
            )
        data = json.loads(result.output)
        assert data["findings_count"] > 0

    def test_changed_only_overrides_paths_argument(self, runner, tmp_path):
        """--changed-only ignora los paths pasados como argumento."""
        (tmp_path / "app.py").write_text("x = 1")
        with patch("vigil.cli._get_changed_files", return_value=[]):
            result = runner.invoke(
                main, ["scan", str(tmp_path), "--changed-only", "--offline"]
            )
        # Returns success with "No changed files"
        assert "No changed files" in result.output


# ===========================================================================
# 6. CONFIGURATION TESTS
# ===========================================================================


class TestConfigurationMerge:
    """Tests de merge de configuracion."""

    def test_cli_overrides_yaml(self, tmp_path):
        """CLI override sobreescribe valor de YAML."""
        config_file = tmp_path / ".vigil.yaml"
        config_file.write_text('fail_on: "low"\n')
        config = load_config(
            config_path=str(config_file),
            cli_overrides={"fail_on": "critical"},
        )
        assert config.fail_on == "critical"

    def test_offline_flag_sets_deps_offline(self):
        """--offline setea deps.offline_mode = True."""
        config = load_config(cli_overrides={"offline": True})
        assert config.deps.offline_mode is True

    def test_quiet_disables_suggestions(self):
        """--quiet desactiva show_suggestions."""
        config = load_config(cli_overrides={"quiet": True})
        assert config.output.show_suggestions is False

    def test_language_filter_from_cli(self):
        """--language se pasa correctamente."""
        config = load_config(cli_overrides={"languages": ["python"]})
        assert config.languages == ["python"]

    def test_categories_from_cli(self):
        """--category se pasa correctamente."""
        config = load_config(cli_overrides={"categories": ["auth", "secrets"]})
        assert config.categories == ["auth", "secrets"]

    def test_exclude_rules_from_cli(self):
        """--exclude-rule se pasa correctamente."""
        config = load_config(cli_overrides={"exclude_rules": ["AUTH-005"]})
        assert config.exclude_rules == ["AUTH-005"]

    def test_rules_filter_from_cli(self):
        """--rule se pasa correctamente."""
        config = load_config(cli_overrides={"rules_filter": ["DEP-001", "DEP-003"]})
        assert config.rules_filter == ["DEP-001", "DEP-003"]

    def test_empty_overrides(self):
        """Sin overrides usa defaults."""
        config = load_config(cli_overrides={})
        assert config.fail_on == "high"
        assert config.deps.offline_mode is False

    def test_none_overrides(self):
        """None overrides usa defaults."""
        config = load_config(cli_overrides=None)
        assert config.fail_on == "high"


class TestConfigGeneration:
    """Tests de generacion de config."""

    def test_strict_strategy(self):
        """Strict strategy genera config mas estricta."""
        content = generate_config_yaml("strict")
        data = yaml.safe_load(content)
        assert data["fail_on"] == "medium"
        assert data["deps"]["min_age_days"] == 60

    def test_relaxed_strategy(self):
        """Relaxed strategy genera config mas permisiva."""
        content = generate_config_yaml("relaxed")
        data = yaml.safe_load(content)
        assert data["fail_on"] == "critical"
        assert data["deps"]["min_age_days"] == 7

    def test_standard_strategy(self):
        """Standard strategy genera config con defaults."""
        content = generate_config_yaml("standard")
        data = yaml.safe_load(content)
        assert data["fail_on"] == "high"

    def test_generated_yaml_is_parseable(self):
        """Generated YAML es parseable por yaml.safe_load."""
        for strategy in ["strict", "standard", "relaxed"]:
            content = generate_config_yaml(strategy)
            data = yaml.safe_load(content)
            assert isinstance(data, dict)

    def test_generated_config_is_loadable(self, tmp_path):
        """Generated config puede cargarse con load_config."""
        for strategy in ["strict", "standard", "relaxed"]:
            content = generate_config_yaml(strategy)
            config_file = tmp_path / f".vigil_{strategy}.yaml"
            config_file.write_text(content)
            config = load_config(config_path=str(config_file))
            assert isinstance(config, ScanConfig)


class TestConfigFindFile:
    """Tests de find_config_file."""

    def test_finds_vigil_yaml(self, tmp_path):
        """Encuentra .vigil.yaml en el directorio actual."""
        (tmp_path / ".vigil.yaml").write_text("fail_on: low")
        result = find_config_file(str(tmp_path))
        assert result is not None
        assert result.name == ".vigil.yaml"

    def test_finds_vigil_yml(self, tmp_path):
        """Encuentra .vigil.yml si no hay .yaml."""
        (tmp_path / ".vigil.yml").write_text("fail_on: low")
        result = find_config_file(str(tmp_path))
        assert result is not None
        assert result.name == ".vigil.yml"

    def test_no_config_returns_none(self, tmp_path):
        """Sin archivo de config retorna None."""
        result = find_config_file(str(tmp_path))
        assert result is None

    def test_prefers_yaml_over_yml(self, tmp_path):
        """Prefiere .vigil.yaml sobre .vigil.yml."""
        (tmp_path / ".vigil.yaml").write_text("fail_on: low")
        (tmp_path / ".vigil.yml").write_text("fail_on: high")
        result = find_config_file(str(tmp_path))
        assert result.name == ".vigil.yaml"


# ===========================================================================
# 7. INTEGRATION TESTS — Engine + Overrides
# ===========================================================================


class TestEngineIntegrationAdvanced:
    """Tests de integracion avanzados del engine."""

    def test_disable_multiple_rules(self):
        """Deshabilitar multiples reglas las quita todas."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            rules={
                "AUTH-004": RuleOverride(enabled=False),
                "AUTH-005": RuleOverride(enabled=False),
                "SEC-001": RuleOverride(enabled=False),
            },
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        disabled = {"AUTH-004", "AUTH-005", "SEC-001"}
        actual = {f.rule_id for f in result.findings}
        assert disabled.isdisjoint(actual), \
            f"Disabled rules found: {disabled & actual}"

    def test_severity_override_affects_ordering(self):
        """Override de severidad cambia el orden de los findings."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            rules={
                "TEST-001": RuleOverride(severity="critical"),
            },
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        test001 = [f for f in result.findings if f.rule_id == "TEST-001"]
        for f in test001:
            assert f.severity == Severity.CRITICAL

    def test_category_filter_auth_only(self):
        """Filtro por categoria 'auth' solo ejecuta AuthAnalyzer."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            categories=["auth"],
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        assert "auth" in result.analyzers_run
        assert "secrets" not in result.analyzers_run
        assert "test-quality" not in result.analyzers_run
        # Solo auth findings
        for f in result.findings:
            assert f.category == Category.AUTH

    def test_exclude_and_rules_filter_combined(self):
        """exclude_rules y rules_filter pueden combinarse."""
        config = ScanConfig(
            rules_filter=["AUTH-004", "AUTH-005"],
            exclude_rules=["AUTH-004"],
        )
        engine = ScanEngine(config)

        result = ScanResult(findings=[
            Finding(
                rule_id="AUTH-004",
                category=Category.AUTH,
                severity=Severity.CRITICAL,
                message="Hardcoded JWT",
                location=Location(file="app.py", line=1),
            ),
            Finding(
                rule_id="AUTH-005",
                category=Category.AUTH,
                severity=Severity.HIGH,
                message="CORS wildcard",
                location=Location(file="app.py", line=2),
            ),
            Finding(
                rule_id="AUTH-001",
                category=Category.AUTH,
                severity=Severity.HIGH,
                message="No auth",
                location=Location(file="app.py", line=3),
            ),
        ])
        engine._apply_rule_overrides(result)
        # rules_filter keeps AUTH-004 and AUTH-005, exclude removes AUTH-004
        rule_ids = {f.rule_id for f in result.findings}
        assert rule_ids == {"AUTH-005"}


class TestScanResultProperties:
    """Tests de ScanResult properties."""

    def test_critical_count(self):
        result = ScanResult(findings=[
            Finding(rule_id="X", category=Category.AUTH, severity=Severity.CRITICAL,
                    message="m", location=Location(file="f")),
            Finding(rule_id="Y", category=Category.AUTH, severity=Severity.HIGH,
                    message="m", location=Location(file="f")),
        ])
        assert result.critical_count == 1

    def test_findings_above_medium(self):
        result = ScanResult(findings=[
            Finding(rule_id="A", category=Category.AUTH, severity=Severity.CRITICAL,
                    message="m", location=Location(file="f")),
            Finding(rule_id="B", category=Category.AUTH, severity=Severity.LOW,
                    message="m", location=Location(file="f")),
            Finding(rule_id="C", category=Category.AUTH, severity=Severity.MEDIUM,
                    message="m", location=Location(file="f")),
        ])
        above = result.findings_above(Severity.MEDIUM)
        assert len(above) == 2  # CRITICAL + MEDIUM

    def test_has_blocking_findings(self):
        result = ScanResult(findings=[
            Finding(rule_id="A", category=Category.AUTH, severity=Severity.LOW,
                    message="m", location=Location(file="f")),
        ])
        assert result.has_blocking_findings is False
        result.findings.append(
            Finding(rule_id="B", category=Category.AUTH, severity=Severity.HIGH,
                    message="m", location=Location(file="f"))
        )
        assert result.has_blocking_findings is True


# ===========================================================================
# 8. FORMATTER EDGE CASES WITH REAL SCANS
# ===========================================================================


class TestFormatterEdgeCases:
    """Edge cases de formatters con datos reales."""

    def test_json_format_zero_findings(self, tmp_path):
        """JSON con 0 findings es JSON valido."""
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])

        from vigil.reports.formatter import get_formatter
        formatter = get_formatter("json")
        output = formatter.format(result)
        data = json.loads(output)
        assert data["findings_count"] == len(data["findings"])

    def test_sarif_format_zero_findings(self, tmp_path):
        """SARIF con 0 findings es valido."""
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])

        from vigil.reports.formatter import get_formatter
        formatter = get_formatter("sarif")
        output = formatter.format(result)
        data = json.loads(output)
        assert data["version"] == "2.1.0"

    def test_junit_format_zero_findings(self, tmp_path):
        """JUnit con 0 findings es XML valido."""
        (tmp_path / "app.py").write_text("x = 1")
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        from vigil.cli import _register_analyzers
        _register_analyzers(engine)
        result = engine.run([str(tmp_path)])

        from vigil.reports.formatter import get_formatter
        formatter = get_formatter("junit")
        output = formatter.format(result)
        root = ET.fromstring(output)
        assert root.tag == "testsuites"

    def test_human_format_with_errors(self, tmp_path):
        """Human format muestra errores de analyzers."""
        result = ScanResult(
            findings=[],
            errors=["Analyzer X failed: some error"],
            files_scanned=0,
            analyzers_run=[],
        )
        from vigil.reports.formatter import get_formatter
        formatter = get_formatter("human", colors=False)
        output = formatter.format(result)
        assert "error" in output.lower() or "Error" in output

    def test_json_format_with_errors(self):
        """JSON format incluye errores."""
        result = ScanResult(
            findings=[],
            errors=["Analyzer boom"],
            files_scanned=5,
            analyzers_run=["auth"],
        )
        from vigil.reports.formatter import get_formatter
        formatter = get_formatter("json")
        output = formatter.format(result)
        data = json.loads(output)
        assert "errors" in data
        assert len(data["errors"]) == 1


# ===========================================================================
# 9. INSECURE FIXTURE COMPLETENESS
# ===========================================================================


class TestInsecureFixtureCompleteness:
    """Verifica que las fixtures inseguras generan los findings esperados."""

    @pytest.fixture(scope="class")
    def insecure_result(self):
        from vigil.cli import _register_analyzers
        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        _register_analyzers(engine)
        return engine.run([str(INSECURE_DIR)])

    def test_auth_005_cors_suppressed_in_test_path(self, insecure_result):
        """AUTH-005 is suppressed because fixtures are under tests/ directory.

        cors_allow_localhost=True (default) suppresses CORS findings
        in paths containing 'test'/'dev'/'local'/'example'.
        """
        rules = {f.rule_id for f in insecure_result.findings}
        # AUTH-005 is correctly suppressed — fixture path contains 'test'
        assert "AUTH-005" not in rules

    def test_auth_005_detected_with_cors_allow_localhost_false(self):
        """AUTH-005 IS detected when cors_allow_localhost=False."""
        from vigil.cli import _register_analyzers
        config = ScanConfig(
            deps={"offline_mode": True},
            auth={"cors_allow_localhost": False},
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        rules = {f.rule_id for f in result.findings}
        assert "AUTH-005" in rules

    def test_auth_004_hardcoded_secret(self, insecure_result):
        rules = {f.rule_id for f in insecure_result.findings}
        assert "AUTH-004" in rules

    def test_auth_002_unprotected_delete(self, insecure_result):
        rules = {f.rule_id for f in insecure_result.findings}
        assert "AUTH-002" in rules

    def test_sec_001_placeholder(self, insecure_result):
        rules = {f.rule_id for f in insecure_result.findings}
        assert "SEC-001" in rules

    def test_sec_003_connection_string(self, insecure_result):
        rules = {f.rule_id for f in insecure_result.findings}
        assert "SEC-003" in rules

    def test_test_001_no_assertions(self, insecure_result):
        rules = {f.rule_id for f in insecure_result.findings}
        assert "TEST-001" in rules

    def test_test_002_trivial_assert(self, insecure_result):
        rules = {f.rule_id for f in insecure_result.findings}
        assert "TEST-002" in rules

    def test_all_findings_have_suggestion_or_metadata(self, insecure_result):
        """Cada finding debe tener suggestion o metadata util."""
        for f in insecure_result.findings:
            has_info = f.suggestion or f.metadata
            assert has_info, (
                f"Finding {f.rule_id} at {f.location.file}:{f.location.line} "
                f"has no suggestion or metadata"
            )

    def test_finding_locations_point_to_real_files(self, insecure_result):
        """Las locations deben apuntar a archivos que existen."""
        for f in insecure_result.findings:
            assert Path(f.location.file).exists(), (
                f"Finding {f.rule_id} points to nonexistent file: {f.location.file}"
            )

    def test_no_duplicate_findings(self, insecure_result):
        """No debe haber findings duplicados exactos (mismo rule_id + file + line)."""
        seen = set()
        for f in insecure_result.findings:
            key = (f.rule_id, f.location.file, f.location.line)
            assert key not in seen, (
                f"Duplicate finding: {f.rule_id} at {f.location.file}:{f.location.line}"
            )
            seen.add(key)


# ===========================================================================
# 10. MERGE CLI OVERRIDES EDGE CASES
# ===========================================================================


class TestMergeCliOverridesEdgeCases:
    """Edge cases de _merge_cli_overrides."""

    def test_empty_languages_not_merged(self):
        """languages=[] no sobreescribe YAML."""
        file_data = {"languages": ["python"]}
        merged = _merge_cli_overrides(file_data, {"languages": []})
        assert merged["languages"] == ["python"]

    def test_none_languages_not_merged(self):
        """languages=None no sobreescribe YAML."""
        file_data = {"languages": ["python"]}
        merged = _merge_cli_overrides(file_data, {"languages": None})
        assert merged["languages"] == ["python"]

    def test_output_preserved_from_yaml(self):
        """Output settings de YAML se preservan cuando CLI no los sobreescribe."""
        file_data = {"output": {"colors": False}}
        merged = _merge_cli_overrides(file_data, {})
        assert merged["output"]["colors"] is False

    def test_offline_only_when_true(self):
        """offline=False no setea deps.offline_mode."""
        file_data = {}
        merged = _merge_cli_overrides(file_data, {"offline": False})
        assert "deps" not in merged

    def test_multiple_overrides_combined(self):
        """Multiples overrides se combinan correctamente."""
        file_data = {"fail_on": "high"}
        merged = _merge_cli_overrides(file_data, {
            "fail_on": "critical",
            "offline": True,
            "languages": ["python"],
            "categories": ["auth"],
            "rules_filter": ["AUTH-005"],
            "exclude_rules": ["AUTH-001"],
            "output_format": "json",
            "verbose": True,
            "quiet": True,
        })
        assert merged["fail_on"] == "critical"
        assert merged["deps"]["offline_mode"] is True
        assert merged["languages"] == ["python"]
        assert merged["categories"] == ["auth"]
        assert merged["rules_filter"] == ["AUTH-005"]
        assert merged["exclude_rules"] == ["AUTH-001"]
        assert merged["output"]["format"] == "json"
        assert merged["output"]["verbose"] is True
        assert merged["output"]["show_suggestions"] is False
