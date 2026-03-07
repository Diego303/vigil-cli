"""Tests para SecretsAnalyzer completo."""

from pathlib import Path

import pytest

from vigil.analyzers.secrets.analyzer import SecretsAnalyzer
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "secrets"


class TestSecretsAnalyzerProtocol:
    """Tests para verificar que SecretsAnalyzer cumple el protocolo."""

    def test_name(self) -> None:
        analyzer = SecretsAnalyzer()
        assert analyzer.name == "secrets"

    def test_category(self) -> None:
        analyzer = SecretsAnalyzer()
        assert analyzer.category == Category.SECRETS

    def test_analyze_returns_list(self) -> None:
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        result = analyzer.analyze([], config)
        assert isinstance(result, list)
        assert result == []


class TestSecretsAnalyzerPlaceholders:
    """Tests para SEC-001: Placeholder secrets."""

    def test_detects_changeme(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "changeme"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1
        assert sec001[0].severity == Severity.CRITICAL

    def test_detects_your_key_here(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('API_KEY = "your-api-key-here"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1

    def test_detects_supersecret(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('JWT_SECRET = "supersecret"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1

    def test_detects_js_placeholder(self, tmp_path: Path) -> None:
        src = tmp_path / "config.js"
        src.write_text("const apiKey = 'your-api-key-here';\n")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1


class TestSecretsAnalyzerLowEntropy:
    """Tests para SEC-002: Low-entropy hardcoded secrets."""

    def test_detects_simple_password(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('DB_PASSWORD = "password123"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        # Could be SEC-001 or SEC-002 depending on pattern match
        sec_findings = [f for f in findings if f.rule_id in ("SEC-001", "SEC-002")]
        assert len(sec_findings) >= 1


class TestSecretsAnalyzerConnectionStrings:
    """Tests para SEC-003: Connection strings con credenciales."""

    def test_detects_postgres_connection(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('DATABASE_URL = "postgresql://admin:secretpass@db.example.com:5432/myapp"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1
        assert sec003[0].severity == Severity.CRITICAL
        assert "Connection string" in sec003[0].message

    def test_detects_mongodb_connection(self, tmp_path: Path) -> None:
        src = tmp_path / "config.js"
        src.write_text(
            "const dbUrl = 'mongodb://admin:mongopass@mongo.example.com:27017/db';\n"
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1

    def test_detects_redis_connection(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('REDIS_URL = "redis://user:redispass@redis.host:6379/0"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1

    def test_env_var_connection_no_finding(self, tmp_path: Path) -> None:
        """Connection string from env var should NOT trigger."""
        src = tmp_path / "app.py"
        src.write_text("DATABASE_URL = os.environ['DATABASE_URL']\n")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) == 0

    def test_connection_string_password_redacted_in_snippet(self, tmp_path: Path) -> None:
        """Password en snippet debe estar redactada."""
        src = tmp_path / "app.py"
        src.write_text('DB = "postgresql://admin:secretpass@host/db"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1
        # Snippet should have password redacted
        assert "secretpass" not in (sec003[0].location.snippet or "")


class TestSecretsAnalyzerEnvDefaults:
    """Tests para SEC-004: Env vars con default values."""

    def test_detects_python_getenv_default(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "sk_test_abc123")\n'
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) >= 1
        assert sec004[0].severity == Severity.HIGH
        assert "STRIPE_SECRET_KEY" in sec004[0].message

    def test_detects_python_os_getenv_default(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('DB_PASS = os.getenv("DB_PASSWORD", "devpassword123")\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) >= 1

    def test_detects_js_env_or_default(self, tmp_path: Path) -> None:
        src = tmp_path / "config.js"
        src.write_text(
            'const jwtSecret = process.env.JWT_SECRET || "devsecret123";\n'
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) >= 1

    def test_no_default_no_finding(self, tmp_path: Path) -> None:
        """Env var sin default no genera finding."""
        src = tmp_path / "app.py"
        src.write_text("SECRET = os.environ.get('SECRET_KEY')\n")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) == 0


class TestSecretsAnalyzerEnvTracer:
    """Tests para SEC-006: Valores copiados de .env.example."""

    def test_detects_copied_value(self, tmp_path: Path) -> None:
        # Create .env.example
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=your-api-key-here\n")

        # Create code that copies the value
        src = tmp_path / "app.py"
        src.write_text('api_key = "your-api-key-here"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) >= 1
        assert sec006[0].severity == Severity.CRITICAL
        assert "API_KEY" in sec006[0].message

    def test_different_value_no_finding(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=your-api-key-here\n")

        src = tmp_path / "app.py"
        src.write_text('api_key = "real-production-key-abc"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) == 0

    def test_env_check_disabled(self, tmp_path: Path) -> None:
        """Si check_env_example=False, no buscar."""
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=your-api-key-here\n")

        src = tmp_path / "app.py"
        src.write_text('api_key = "your-api-key-here"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        config.secrets.check_env_example = False
        findings = analyzer.analyze([str(src)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) == 0

    def test_fixture_copies_env_example(self) -> None:
        """Integration test con fixture que copia .env.example."""
        fixture_dir = FIXTURES_DIR
        env_example = fixture_dir / ".env.example"
        code_file = fixture_dir / "copies_env_example.py"

        if not env_example.exists() or not code_file.exists():
            pytest.skip("Fixtures not found")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(code_file)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) >= 1


class TestSecretsAnalyzerNegative:
    """Tests negativos — codigo seguro NO debe generar findings."""

    def test_env_var_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            "import os\n"
            "SECRET_KEY = os.environ['SECRET_KEY']\n"
            "API_KEY = os.getenv('API_KEY')\n"
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_non_sensitive_assignments(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'APP_NAME = "my-application"\n'
            'VERSION = "1.0.0"\n'
            "DEBUG = True\n"
            "MAX_RETRIES = 3\n"
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_non_code_files_ignored(self) -> None:
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze(["/some/readme.md", "/some/data.json"], config)
        assert findings == []


class TestSecretsAnalyzerEdgeCases:
    """Tests para edge cases."""

    def test_empty_file(self, tmp_path: Path) -> None:
        src = tmp_path / "empty.py"
        src.write_text("")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert findings == []

    def test_nonexistent_file(self) -> None:
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze(["/nonexistent/file.py"], config)
        assert findings == []

    def test_binary_file_handled(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert isinstance(findings, list)

    def test_comments_ignored_python(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            '# SECRET_KEY = "changeme"\n'
            '# DATABASE_URL = "postgresql://a:b@c/d"\n'
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) == 0

    def test_comments_ignored_js(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "// const password = 'changeme';\n"
            "// const dbUrl = 'postgresql://a:b@c/d';\n"
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) == 0

    def test_fixture_insecure_secrets_python(self) -> None:
        """Integration test con fixture insegura Python."""
        fixture = FIXTURES_DIR / "insecure_secrets.py"
        if not fixture.exists():
            pytest.skip("Fixture not found")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(fixture)], config)

        rule_ids = {f.rule_id for f in findings}
        # Should detect multiple issues
        assert len(findings) >= 3
        # Should find connection strings and secrets
        assert "SEC-003" in rule_ids or "SEC-001" in rule_ids

    def test_fixture_secure_code(self) -> None:
        """Integration test con fixture segura."""
        fixture = FIXTURES_DIR / "secure_code.py"
        if not fixture.exists():
            pytest.skip("Fixture not found")

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(fixture)], config)

        # Secure code should have no findings
        assert len(findings) == 0

    def test_multiple_secrets_in_one_file(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'API_KEY = "your-api-key-here"\n'
            'SECRET_KEY = "changeme"\n'
            'DB_URL = "postgresql://admin:pass@localhost/db"\n'
        )

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) >= 2  # At least placeholder + connection string
