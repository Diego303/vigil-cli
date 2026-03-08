"""End-to-end integration tests — real analyzers on realistic fixtures.

Estos tests ejecutan el pipeline completo: CLI -> engine -> analyzers reales
-> formatters, contra fixtures que representan codigo AI-generated real con
problemas de seguridad.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from vigil.cli import ExitCode, main
from vigil.config.schema import RuleOverride, ScanConfig
from vigil.core.engine import ScanEngine
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "integration"
INSECURE_DIR = FIXTURES_DIR / "insecure_project"
CLEAN_DIR = FIXTURES_DIR / "clean_project"


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Engine-level integration tests (real analyzers, no CLI)
# ---------------------------------------------------------------------------


class TestEngineIntegrationInsecureProject:
    """Ejecuta el engine con todos los analyzers contra el proyecto inseguro."""

    @pytest.fixture
    def scan_result(self):
        """Ejecuta scan completo del proyecto inseguro en modo offline."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        return engine.run([str(INSECURE_DIR)])

    def test_finds_multiple_categories(self, scan_result):
        """El scan debe encontrar findings de multiples categorias."""
        categories = {f.category for f in scan_result.findings}
        # Al menos auth, secrets, y test-quality (deps no genera en offline)
        assert Category.AUTH in categories
        assert Category.SECRETS in categories
        assert Category.TEST_QUALITY in categories

    def test_all_analyzers_run(self, scan_result):
        """Los 4 analyzers deben ejecutarse."""
        assert "dependency" in scan_result.analyzers_run
        assert "auth" in scan_result.analyzers_run
        assert "secrets" in scan_result.analyzers_run
        assert "test-quality" in scan_result.analyzers_run

    def test_no_errors(self, scan_result):
        """Ningun analyzer debe crashear."""
        assert len(scan_result.errors) == 0

    def test_files_scanned(self, scan_result):
        """Debe escanear archivos Python y JavaScript."""
        assert scan_result.files_scanned > 0

    def test_duration_recorded(self, scan_result):
        assert scan_result.duration_seconds > 0

    def test_auth_findings_present(self, scan_result):
        """Debe detectar problemas de auth (CORS, hardcoded secret, etc.)."""
        auth_findings = [f for f in scan_result.findings if f.category == Category.AUTH]
        # AUTH-004 (hardcoded secret) y AUTH-005 (CORS *) son los mas probables
        assert len(auth_findings) > 0, "Expected auth findings from insecure fixtures"

    def test_secrets_findings_present(self, scan_result):
        """Debe detectar secrets mal gestionados."""
        sec_findings = [f for f in scan_result.findings if f.category == Category.SECRETS]
        assert len(sec_findings) > 0, "Expected secrets findings from insecure fixtures"

    def test_test_quality_findings_present(self, scan_result):
        """Debe detectar test theater."""
        test_findings = [f for f in scan_result.findings
                         if f.category == Category.TEST_QUALITY]
        test_rules = {f.rule_id for f in test_findings}
        # TEST-001 (no assertions) deberia estar
        assert "TEST-001" in test_rules, "Expected TEST-001 for test without assertions"

    def test_findings_ordered_by_severity(self, scan_result):
        """Los findings deben estar ordenados por severidad (critical primero)."""
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        for i in range(len(scan_result.findings) - 1):
            current = severity_order[scan_result.findings[i].severity]
            next_sev = severity_order[scan_result.findings[i + 1].severity]
            assert current <= next_sev, (
                f"Findings not ordered: {scan_result.findings[i].severity} "
                f"before {scan_result.findings[i + 1].severity}"
            )

    def test_every_finding_has_required_fields(self, scan_result):
        """Cada finding debe tener los campos requeridos."""
        for f in scan_result.findings:
            assert f.rule_id, "Finding missing rule_id"
            assert f.category, "Finding missing category"
            assert f.severity, "Finding missing severity"
            assert f.message, "Finding missing message"
            assert f.location, "Finding missing location"
            assert f.location.file, "Finding missing location.file"

    def test_finding_messages_are_actionable(self, scan_result):
        """Los mensajes no deben ser genericos."""
        for f in scan_result.findings:
            assert len(f.message) > 20, (
                f"Message too short for {f.rule_id}: {f.message}"
            )
            # No deben ser genericos
            assert "possible issue" not in f.message.lower()
            assert "something wrong" not in f.message.lower()


class TestEngineIntegrationCleanProject:
    """Verifica que el proyecto limpio no genera findings (falsos positivos)."""

    @pytest.fixture
    def scan_result(self):
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        return engine.run([str(CLEAN_DIR)])

    def test_no_auth_findings(self, scan_result):
        """Codigo limpio no debe generar findings de auth."""
        auth_findings = [f for f in scan_result.findings if f.category == Category.AUTH]
        # Puede haber algunos (e.g., si el login POST detecta AUTH-002),
        # pero no deberia haber AUTH-004 o AUTH-005
        auth_rules = {f.rule_id for f in auth_findings}
        assert "AUTH-004" not in auth_rules, "False positive: AUTH-004 on clean code"
        assert "AUTH-005" not in auth_rules, "False positive: AUTH-005 on clean code"

    def test_no_secret_findings(self, scan_result):
        """Codigo limpio no debe generar findings de secrets."""
        sec_findings = [f for f in scan_result.findings if f.category == Category.SECRETS]
        sec_rules = {f.rule_id for f in sec_findings}
        assert "SEC-001" not in sec_rules, "False positive: SEC-001 on clean code"
        assert "SEC-002" not in sec_rules, "False positive: SEC-002 on clean code"
        assert "SEC-003" not in sec_rules, "False positive: SEC-003 on clean code"

    def test_no_test_quality_findings(self, scan_result):
        """Tests bien escritos no deben generar findings."""
        test_findings = [f for f in scan_result.findings
                         if f.category == Category.TEST_QUALITY]
        test_rules = {f.rule_id for f in test_findings}
        assert "TEST-001" not in test_rules, "False positive: TEST-001 on clean tests"
        assert "TEST-002" not in test_rules, "False positive: TEST-002 on clean tests"

    def test_all_analyzers_run(self, scan_result):
        """Todos los analyzers deben ejecutarse incluso sin findings."""
        assert len(scan_result.analyzers_run) == 4

    def test_no_errors(self, scan_result):
        assert len(scan_result.errors) == 0


# ---------------------------------------------------------------------------
# Engine + rule override integration
# ---------------------------------------------------------------------------


class TestEngineRuleOverrides:
    """Verifica que rule overrides funcionan end-to-end."""

    def test_disable_rule(self):
        """Deshabilitar una regla la quita de los resultados."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            rules={"AUTH-005": RuleOverride(enabled=False)},
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        assert not any(f.rule_id == "AUTH-005" for f in result.findings)

    def test_severity_override(self):
        """Override de severidad cambia el finding."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            rules={"TEST-001": RuleOverride(severity="low")},
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        test001 = [f for f in result.findings if f.rule_id == "TEST-001"]
        for f in test001:
            assert f.severity == Severity.LOW

    def test_category_filter(self):
        """Filtro de categoria solo ejecuta los analyzers de esa categoria."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            categories=["test-quality"],
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        assert "test-quality" in result.analyzers_run
        # Los otros no deben haber corrido
        assert "auth" not in result.analyzers_run
        assert "secrets" not in result.analyzers_run
        assert "dependency" not in result.analyzers_run

    def test_exclude_rule(self):
        """--exclude-rule quita findings de esa regla."""
        from vigil.cli import _register_analyzers

        config = ScanConfig(
            deps={"offline_mode": True},
            exclude_rules=["AUTH-004", "AUTH-005"],
        )
        engine = ScanEngine(config)
        _register_analyzers(engine)
        result = engine.run([str(INSECURE_DIR)])
        excluded = {f.rule_id for f in result.findings}
        assert "AUTH-004" not in excluded
        assert "AUTH-005" not in excluded


# ---------------------------------------------------------------------------
# CLI-level integration tests (Click CliRunner)
# ---------------------------------------------------------------------------


class TestCLIIntegrationScan:
    """Tests end-to-end via CLI con CliRunner."""

    def test_scan_insecure_produces_findings(self, runner):
        """vigil scan en proyecto inseguro produce findings."""
        result = runner.invoke(
            main, ["scan", str(INSECURE_DIR), "--offline"]
        )
        # Deberia tener exit code 1 (findings above high threshold)
        assert result.exit_code == ExitCode.FINDINGS
        assert "findings" in result.output

    def test_scan_insecure_json(self, runner):
        """JSON output contiene findings validos."""
        result = runner.invoke(
            main, ["scan", str(INSECURE_DIR), "--format", "json", "--offline"]
        )
        data = json.loads(result.output)
        assert data["findings_count"] > 0
        assert len(data["findings"]) == data["findings_count"]
        # Verificar estructura de cada finding
        for f in data["findings"]:
            assert "rule_id" in f
            assert "category" in f
            assert "severity" in f
            assert "message" in f
            assert "location" in f
            assert "file" in f["location"]

    def test_scan_insecure_sarif(self, runner):
        """SARIF output es valido y contiene findings."""
        result = runner.invoke(
            main, ["scan", str(INSECURE_DIR), "--format", "sarif", "--offline"]
        )
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        run = data["runs"][0]
        assert len(run["results"]) > 0
        # Cada resultado debe tener ruleId y location
        for r in run["results"]:
            assert "ruleId" in r
            assert "locations" in r

    def test_scan_insecure_junit(self, runner):
        """JUnit XML output es valido y contiene failures."""
        result = runner.invoke(
            main, ["scan", str(INSECURE_DIR), "--format", "junit", "--offline"]
        )
        root = ET.fromstring(result.output)
        suite = root.find("testsuite")
        failures = int(suite.get("failures", "0"))
        assert failures > 0

    def test_scan_insecure_to_file(self, runner, tmp_path):
        """--output escribe el reporte a un archivo."""
        output_file = tmp_path / "report.json"
        result = runner.invoke(
            main, [
                "scan", str(INSECURE_DIR),
                "--format", "json",
                "--output", str(output_file),
                "--offline",
            ]
        )
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "findings" in data

    def test_scan_clean_no_findings(self, runner):
        """vigil scan en proyecto limpio no produce findings de alto riesgo."""
        result = runner.invoke(
            main, [
                "scan", str(CLEAN_DIR),
                "--offline", "--fail-on", "critical",
            ]
        )
        # No deberia haber CRITICAL findings en proyecto limpio
        assert result.exit_code == ExitCode.SUCCESS

    def test_scan_with_category_filter(self, runner):
        """--category filtra los analyzers que corren."""
        result = runner.invoke(
            main, [
                "scan", str(INSECURE_DIR),
                "--category", "test-quality",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        categories = {f["category"] for f in data["findings"]}
        assert categories == {"test-quality"} or len(categories) == 0

    def test_scan_with_rule_filter(self, runner):
        """--rule filtra a solo esa regla."""
        result = runner.invoke(
            main, [
                "scan", str(INSECURE_DIR),
                "--rule", "AUTH-005",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        rule_ids = {f["rule_id"] for f in data["findings"]}
        assert rule_ids <= {"AUTH-005"}

    def test_scan_with_exclude_rule(self, runner):
        """--exclude-rule quita una regla especifica."""
        result = runner.invoke(
            main, [
                "scan", str(INSECURE_DIR),
                "--exclude-rule", "AUTH-005",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        rule_ids = {f["rule_id"] for f in data["findings"]}
        assert "AUTH-005" not in rule_ids

    def test_scan_quiet_mode(self, runner):
        """--quiet solo muestra findings, no header ni summary."""
        result = runner.invoke(
            main, ["scan", str(INSECURE_DIR), "--quiet", "--offline"]
        )
        # No deberia tener linea de "vigil v..." ni separador
        assert "scanning" not in result.output.lower()
        assert "analyzers:" not in result.output

    def test_scan_verbose_mode(self, runner):
        """--verbose no crashea."""
        result = runner.invoke(
            main, ["scan", str(INSECURE_DIR), "--verbose", "--offline"]
        )
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_scan_fail_on_critical(self, runner):
        """--fail-on critical solo falla con findings CRITICAL."""
        result = runner.invoke(
            main, [
                "scan", str(INSECURE_DIR),
                "--fail-on", "critical",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        criticals = [f for f in data["findings"] if f["severity"] == "critical"]
        if criticals:
            assert result.exit_code == ExitCode.FINDINGS
        else:
            assert result.exit_code == ExitCode.SUCCESS

    def test_scan_language_filter(self, runner):
        """--language python solo escanea archivos Python."""
        result = runner.invoke(
            main, [
                "scan", str(INSECURE_DIR),
                "--language", "python",
                "--format", "json",
                "--offline",
            ]
        )
        data = json.loads(result.output)
        for f in data["findings"]:
            file_path = f["location"]["file"]
            # Los findings deben venir de archivos Python (o dependency files)
            assert (
                file_path.endswith(".py")
                or file_path.endswith(".txt")
                or file_path.endswith(".toml")
                or file_path.endswith(".json")
            ), f"Unexpected file in Python-only scan: {file_path}"


class TestCLIIntegrationDeps:
    """Tests end-to-end del subcomando deps."""

    def test_deps_on_insecure_offline(self, runner):
        """vigil deps en modo offline escanea typosquatting."""
        result = runner.invoke(
            main, ["deps", str(INSECURE_DIR), "--offline"]
        )
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_deps_json_format(self, runner):
        result = runner.invoke(
            main, [
                "deps", str(INSECURE_DIR),
                "--format", "json", "--offline",
            ]
        )
        data = json.loads(result.output)
        assert "findings" in data
        # En offline, solo deberia haber DEP-003 (typosquatting)
        for f in data["findings"]:
            assert f["category"] == "dependency"


class TestCLIIntegrationTests:
    """Tests end-to-end del subcomando tests."""

    def test_tests_on_insecure_fixtures(self, runner):
        """vigil tests detecta test theater en las fixtures."""
        result = runner.invoke(
            main, ["tests", str(INSECURE_DIR)]
        )
        assert result.exit_code == ExitCode.FINDINGS

    def test_tests_json_format(self, runner):
        result = runner.invoke(
            main, ["tests", str(INSECURE_DIR), "--format", "json"]
        )
        data = json.loads(result.output)
        categories = {f["category"] for f in data["findings"]}
        assert categories <= {"test-quality"}

    def test_tests_on_clean(self, runner):
        """Clean tests no deben generar findings de test-quality."""
        result = runner.invoke(
            main, ["tests", str(CLEAN_DIR)]
        )
        # Clean tests should not have TEST-001 or TEST-002
        assert result.exit_code == ExitCode.SUCCESS


class TestCLIIntegrationInit:
    """Tests end-to-end del subcomando init."""

    @pytest.mark.parametrize("strategy", ["strict", "standard", "relaxed"])
    def test_init_generates_valid_yaml(self, runner, tmp_path, strategy):
        """init genera YAML valido que se puede cargar."""
        import yaml

        result = runner.invoke(main, ["init", "--strategy", strategy, str(tmp_path)])
        assert result.exit_code == 0
        config_path = tmp_path / ".vigil.yaml"
        assert config_path.exists()
        data = yaml.safe_load(config_path.read_text())
        assert isinstance(data, dict)
        assert "fail_on" in data

    def test_init_and_scan_with_config(self, runner, tmp_path):
        """init genera config que se puede usar en scan."""
        # Generar config
        runner.invoke(main, ["init", str(tmp_path)])
        # Crear un archivo para escanear
        (tmp_path / "app.py").write_text("x = 1")
        # Scan con la config generada
        config_path = tmp_path / ".vigil.yaml"
        result = runner.invoke(
            main, [
                "scan", str(tmp_path),
                "--config", str(config_path),
                "--offline",
            ]
        )
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)


# ---------------------------------------------------------------------------
# Changed-only integration tests
# ---------------------------------------------------------------------------


class TestChangedOnlyIntegration:
    """Tests para --changed-only flag."""

    def test_changed_only_no_changes(self, runner, tmp_path):
        """--changed-only sin cambios reporta 'no changed files'."""
        (tmp_path / "app.py").write_text("x = 1")
        with patch("vigil.cli._get_changed_files", return_value=[]):
            result = runner.invoke(
                main, ["scan", str(tmp_path), "--changed-only", "--offline"]
            )
        assert result.exit_code == ExitCode.SUCCESS
        assert "No changed files" in result.output

    def test_changed_only_with_files(self, runner, tmp_path):
        """--changed-only con archivos cambiados los escanea."""
        (tmp_path / "app.py").write_text("x = 1")
        with patch("vigil.cli._get_changed_files",
                    return_value=[str(tmp_path / "app.py")]):
            result = runner.invoke(
                main, ["scan", str(tmp_path), "--changed-only", "--offline"]
            )
        assert result.exit_code in (ExitCode.SUCCESS, ExitCode.FINDINGS)

    def test_changed_only_returns_files(self):
        """_get_changed_files retorna archivos del directorio actual."""
        from vigil.cli import _get_changed_files
        # En el repositorio vigil-cli, deberia retornar archivos cambiados
        files = _get_changed_files()
        # No podemos verificar contenido especifico, solo que no crashea
        assert isinstance(files, list)


# ---------------------------------------------------------------------------
# Formatter integration with real scan results
# ---------------------------------------------------------------------------


class TestFormatterIntegrationReal:
    """Verifica formatters con resultado de scan real (no fake)."""

    @pytest.fixture
    def real_scan_result(self):
        from vigil.cli import _register_analyzers

        config = ScanConfig(deps={"offline_mode": True})
        engine = ScanEngine(config)
        _register_analyzers(engine)
        return engine.run([str(INSECURE_DIR)])

    def test_human_formatter_real(self, real_scan_result):
        from vigil.reports.formatter import get_formatter

        formatter = get_formatter("human", colors=False)
        output = formatter.format(real_scan_result)
        assert "findings" in output
        assert "files" in output

    def test_json_formatter_real(self, real_scan_result):
        from vigil.reports.formatter import get_formatter

        formatter = get_formatter("json")
        output = formatter.format(real_scan_result)
        data = json.loads(output)
        assert data["findings_count"] == len(data["findings"])
        assert data["files_scanned"] > 0

    def test_sarif_formatter_real(self, real_scan_result):
        from vigil.reports.formatter import get_formatter

        formatter = get_formatter("sarif")
        output = formatter.format(real_scan_result)
        data = json.loads(output)
        assert data["version"] == "2.1.0"
        run = data["runs"][0]
        # Cada resultado debe tener un rule correspondiente
        rule_ids_defined = {r["id"] for r in run["tool"]["driver"]["rules"]}
        for r in run["results"]:
            assert r["ruleId"] in rule_ids_defined

    def test_junit_formatter_real(self, real_scan_result):
        from vigil.reports.formatter import get_formatter

        formatter = get_formatter("junit")
        output = formatter.format(real_scan_result)
        root = ET.fromstring(output)
        suite = root.find("testsuite")
        assert int(suite.get("failures", "0")) == len(real_scan_result.findings)

    def test_json_roundtrip(self, real_scan_result):
        """JSON output es parseable y contiene toda la info."""
        from vigil.reports.formatter import get_formatter

        formatter = get_formatter("json")
        output = formatter.format(real_scan_result)
        data = json.loads(output)
        # Verificar summary
        assert "summary" in data
        assert data["summary"]["total_findings"] == len(data["findings"])
        assert data["summary"]["files_scanned"] == data["files_scanned"]


# ---------------------------------------------------------------------------
# Analyzer isolation tests (un error en un analyzer no crashea el scan)
# ---------------------------------------------------------------------------


class TestAnalyzerIsolation:
    """Verifica que un analyzer que falla no crashea todo el scan."""

    def test_failing_analyzer_captured(self, tmp_path):
        """Un analyzer que lanza excepcion se captura en errors."""
        (tmp_path / "app.py").write_text("x = 1")

        class FailingAnalyzer:
            name = "failing"
            category = Category.AUTH

            def analyze(self, files, config):
                raise RuntimeError("Analyzer crashed!")

        config = ScanConfig()
        engine = ScanEngine(config)
        engine.register_analyzer(FailingAnalyzer())
        result = engine.run([str(tmp_path)])

        assert len(result.errors) == 1
        assert "Analyzer failing failed" in result.errors[0]
        assert "crashed" in result.errors[0].lower()

    def test_failing_analyzer_doesnt_stop_others(self, tmp_path):
        """Otros analyzers siguen corriendo despues de un fallo."""
        (tmp_path / "app.py").write_text("x = 1")

        class FailingAnalyzer:
            name = "failing"
            category = Category.AUTH

            def analyze(self, files, config):
                raise RuntimeError("boom")

        class WorkingAnalyzer:
            name = "working"
            category = Category.SECRETS

            def analyze(self, files, config):
                return []

        config = ScanConfig()
        engine = ScanEngine(config)
        engine.register_analyzer(FailingAnalyzer())
        engine.register_analyzer(WorkingAnalyzer())
        result = engine.run([str(tmp_path)])

        assert "working" in result.analyzers_run
        assert len(result.errors) == 1
