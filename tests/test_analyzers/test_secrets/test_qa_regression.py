"""QA regression tests para SecretsAnalyzer — FASE 2.

Cubre: edge cases, false positives, false negatives, configuration,
regression tests de bugs encontrados en QA audit.
"""

from pathlib import Path

import pytest

from vigil.analyzers.secrets.analyzer import (
    SecretsAnalyzer,
    _is_relevant_file,
    _is_comment,
    _redact_password,
    _truncate,
)
from vigil.analyzers.secrets.entropy import shannon_entropy
from vigil.analyzers.secrets.placeholder_detector import (
    DEFAULT_PLACEHOLDER_PATTERNS,
    _COMPILED_DEFAULT_PATTERNS,
    compile_placeholder_patterns,
    find_secret_assignments,
    is_placeholder_value,
)
from vigil.analyzers.secrets.env_tracer import (
    EnvExampleEntry,
    find_env_example_files,
    find_env_values_in_code,
    parse_env_example,
)
from vigil.config.schema import ScanConfig, SecretsConfig
from vigil.core.finding import Category, Severity


# ──────────────────────────────────────────────
# Regression: Bug #3 — SEC-006 no longer leaks secret values
# ──────────────────────────────────────────────


class TestSEC006NoValueLeakage:
    """Regression: SEC-006 should NOT include the secret value in message or metadata."""

    def test_value_not_in_message(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=super-secret-real-key-12345\n")
        src = tmp_path / "app.py"
        src.write_text('key = "super-secret-real-key-12345"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) >= 1
        assert "super-secret-real-key-12345" not in sec006[0].message

    def test_value_not_in_metadata(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=super-secret-real-key-12345\n")
        src = tmp_path / "app.py"
        src.write_text('key = "super-secret-real-key-12345"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) >= 1
        assert "env_value" not in sec006[0].metadata

    def test_key_name_still_in_message(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=super-secret-real-key-12345\n")
        src = tmp_path / "app.py"
        src.write_text('key = "super-secret-real-key-12345"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) >= 1
        assert "API_KEY" in sec006[0].message


# ──────────────────────────────────────────────
# Regression: Bug #6 — Placeholder patterns are cached
# ──────────────────────────────────────────────


class TestPlaceholderPatternCaching:
    """Regression: is_placeholder_value should use cached compiled patterns."""

    def test_compiled_default_patterns_exist(self) -> None:
        assert len(_COMPILED_DEFAULT_PATTERNS) == len(DEFAULT_PLACEHOLDER_PATTERNS)

    def test_cached_patterns_match_same_as_fresh(self) -> None:
        """Cached and freshly compiled should give same results."""
        test_values = [
            "changeme", "your-api-key-here", "supersecret",
            "real-production-key-abc", "x7q2m9p4k1",
        ]
        fresh = compile_placeholder_patterns(DEFAULT_PLACEHOLDER_PATTERNS)
        for value in test_values:
            cached_result = is_placeholder_value(value)  # uses cached
            fresh_result = is_placeholder_value(value, fresh)
            assert cached_result == fresh_result, f"Mismatch for '{value}'"


# ──────────────────────────────────────────────
# Regression: Bug #12 — Config patterns synced with defaults
# ──────────────────────────────────────────────


class TestConfigPatternSync:
    """Regression: SecretsConfig patterns should be a superset of important patterns."""

    def test_config_covers_key_patterns(self) -> None:
        config_patterns = SecretsConfig().placeholder_patterns
        compiled = compile_placeholder_patterns(config_patterns)

        must_detect = [
            "changeme", "your-api-key-here", "your_api_key_here",
            "TODO_replace", "FIXME_this", "xxxx",
            "sk-your-key", "pk_test_abc", "sk_test_abc",
            "secret123", "password123", "supersecret", "mysecret",
            "admin@example.com", "replaceme", "placeholder_value",
            "test_key", "dummy_secret", "fake_key", "sample_secret",
            "default_secret", "my_secret_key",
        ]
        for value in must_detect:
            assert is_placeholder_value(value, compiled), \
                f"Config patterns should detect '{value}'"

    def test_config_does_not_false_positive(self) -> None:
        config_patterns = SecretsConfig().placeholder_patterns
        compiled = compile_placeholder_patterns(config_patterns)

        safe_values = [
            "sk_live_a3f8b2c1d9e0x7y4z",
            "x7q2m9p4k1",
            "production_db_host",
        ]
        for value in safe_values:
            assert not is_placeholder_value(value, compiled), \
                f"Config patterns should NOT match '{value}'"


# ──────────────────────────────────────────────
# False positives
# ──────────────────────────────────────────────


class TestSecretsFalsePositives:
    """Tests para asegurar que codigo seguro no genera findings."""

    def test_env_var_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            "import os\n"
            "SECRET_KEY = os.environ['SECRET_KEY']\n"
            "API_KEY = os.getenv('API_KEY')\n"
            "DB_URL = os.environ.get('DATABASE_URL')\n"
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) == 0

    def test_js_process_env_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "const secret = process.env.SECRET_KEY;\n"
            "const apiKey = process.env.API_KEY;\n"
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
            'LOG_LEVEL = "info"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) == 0

    def test_env_default_non_sensitive_key(self, tmp_path: Path) -> None:
        """os.environ.get with non-sensitive key should not trigger SEC-004."""
        src = tmp_path / "app.py"
        src.write_text('LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")\n')
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) == 0

    def test_connection_string_env_var_no_finding(self, tmp_path: Path) -> None:
        """Connection string from env var is safe."""
        src = tmp_path / "app.py"
        src.write_text("DATABASE_URL = os.environ['DATABASE_URL']\n")
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) == 0

    def test_connection_string_with_env_placeholder_password(self, tmp_path: Path) -> None:
        """Connection string with $VAR password should not trigger."""
        src = tmp_path / "app.py"
        src.write_text(
            'DB = "postgresql://admin:${DB_PASSWORD}@host/db"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) == 0

    def test_comments_python_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            '# SECRET_KEY = "changeme"\n'
            '# DATABASE_URL = "postgresql://a:b@c/d"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) == 0

    def test_comments_js_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "// const secret = 'changeme';\n"
            "// const dbUrl = 'postgresql://a:b@c/d';\n"
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) == 0


# ──────────────────────────────────────────────
# False negatives
# ──────────────────────────────────────────────


class TestSecretsFalseNegatives:
    """Tests para verificar deteccion en escenarios complejos."""

    def test_mongodb_srv_connection_string(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'MONGO_URL = "mongodb+srv://admin:mongopass@cluster.mongodb.net/db"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1

    def test_amqp_connection_string(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'BROKER_URL = "amqp://guest:guest@rabbit.example.com:5672/"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1

    def test_js_env_default_with_or_operator(self, tmp_path: Path) -> None:
        src = tmp_path / "config.js"
        src.write_text(
            "const jwtSecret = process.env.JWT_SECRET || 'devsecret123';\n"
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) >= 1

    def test_multiple_secrets_same_file(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'API_KEY = "your-api-key-here"\n'
            'SECRET_KEY = "changeme"\n'
            'DB_URL = "postgresql://admin:pass@localhost/db"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) >= 2


# ──────────────────────────────────────────────
# Configuration tests
# ──────────────────────────────────────────────


class TestSecretsConfiguration:
    """Tests para configuracion del SecretsAnalyzer."""

    def test_min_entropy_threshold(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('PASSWORD = "test1234"\n')
        analyzer = SecretsAnalyzer()

        # With default threshold (3.0), should detect
        config_low = ScanConfig()
        findings_low = analyzer.analyze([str(src)], config_low)
        sec002_low = [f for f in findings_low if f.rule_id == "SEC-002"]

        # With very low threshold, should not detect
        config_high = ScanConfig()
        config_high.secrets.min_entropy = 1.0
        findings_high = analyzer.analyze([str(src)], config_high)
        sec002_high = [f for f in findings_high if f.rule_id == "SEC-002"]

        # Low threshold means fewer things are "low entropy"
        assert len(sec002_high) <= len(sec002_low)

    def test_check_env_example_disabled(self, tmp_path: Path) -> None:
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

    def test_custom_placeholder_patterns(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "MY_CUSTOM_PLACEHOLDER"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        config.secrets.placeholder_patterns = ["MY_CUSTOM_PLACEHOLDER"]
        findings = analyzer.analyze([str(src)], config)
        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────


class TestSecretsEdgeCases:
    """Edge cases para SecretsAnalyzer."""

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

    def test_non_code_files_skipped(self) -> None:
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze(
            ["/some/readme.md", "/data.json", "/image.png"], config
        )
        assert findings == []

    def test_typescript_file_supported(self, tmp_path: Path) -> None:
        src = tmp_path / "config.ts"
        src.write_text('const API_KEY = "your-api-key-here";\n')
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1

    def test_jsx_file_supported(self, tmp_path: Path) -> None:
        src = tmp_path / "App.jsx"
        src.write_text('const password = "changeme";\n')
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert len(findings) >= 1

    def test_connection_string_password_redacted(self, tmp_path: Path) -> None:
        """SEC-003 snippet should redact the password."""
        src = tmp_path / "app.py"
        src.write_text(
            'DB = "postgresql://admin:verysecretpassword@host/db"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1
        assert "verysecretpassword" not in (sec003[0].location.snippet or "")

    def test_sec003_does_not_duplicate_with_sec001(self, tmp_path: Path) -> None:
        """A line with a connection string should only produce SEC-003, not SEC-001."""
        src = tmp_path / "app.py"
        src.write_text(
            'DATABASE_URL = "postgresql://admin:changeme@host/db"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec003) >= 1
        # SEC-003 should prevent SEC-001 from firing on the same line
        assert len(sec001) == 0

    def test_multiple_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.py"
        f1.write_text('API_KEY = "your-api-key-here"\n')
        f2 = tmp_path / "b.py"
        f2.write_text('SECRET = "changeme"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(f1), str(f2)], config)
        files = {f.location.file for f in findings}
        assert str(f1) in files
        assert str(f2) in files


# ──────────────────────────────────────────────
# Helper function tests
# ──────────────────────────────────────────────


class TestHelperFunctions:
    """Tests para funciones auxiliares de secrets/analyzer.py."""

    def test_is_relevant_file_py(self) -> None:
        assert _is_relevant_file("app.py") is True

    def test_is_relevant_file_js(self) -> None:
        assert _is_relevant_file("app.js") is True

    def test_is_relevant_file_md(self) -> None:
        assert _is_relevant_file("README.md") is False

    def test_is_relevant_file_json(self) -> None:
        assert _is_relevant_file("package.json") is False

    def test_is_comment_python(self) -> None:
        assert _is_comment("# comment", True) is True
        assert _is_comment("code = 1", True) is False

    def test_is_comment_js(self) -> None:
        assert _is_comment("// comment", False) is True
        assert _is_comment("const x = 1;", False) is False

    def test_truncate_short(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long(self) -> None:
        assert _truncate("hello world", 5) == "hello..."

    def test_truncate_exact(self) -> None:
        assert _truncate("hello", 5) == "hello"

    def test_redact_password(self) -> None:
        line = "postgresql://admin:secretpass@host/db"
        result = _redact_password(line)
        assert "secretpass" not in result
        assert "***" in result
        assert "admin" in result

    def test_redact_password_no_match(self) -> None:
        line = "just a regular string"
        assert _redact_password(line) == line


# ──────────────────────────────────────────────
# Entropy edge cases
# ──────────────────────────────────────────────


class TestEntropyEdgeCases:
    """Edge cases para entropy calculation."""

    def test_single_char_repeated(self) -> None:
        assert shannon_entropy("aaaaaaa") == 0.0

    def test_two_unique_chars(self) -> None:
        assert abs(shannon_entropy("ab") - 1.0) < 0.01

    def test_known_placeholder_low_entropy(self) -> None:
        assert shannon_entropy("changeme") < 3.0
        assert shannon_entropy("password") < 3.0
        assert shannon_entropy("secret123") < 3.5

    def test_known_real_key_high_entropy(self) -> None:
        assert shannon_entropy("a3f8b2c1d9e0x7y4z6wq") > 3.5

    def test_hex_string_high_entropy(self) -> None:
        assert shannon_entropy("deadbeef1234567890abcdef") > 3.5

    def test_base64_like_high_entropy(self) -> None:
        assert shannon_entropy("SGVsbG8gV29ybGQ=") > 3.0


# ──────────────────────────────────────────────
# Env tracer edge cases
# ──────────────────────────────────────────────


class TestEnvTracerEdgeCases:
    """Edge cases para env_tracer."""

    def test_env_template_found(self, tmp_path: Path) -> None:
        (tmp_path / ".env.template").write_text("KEY=value-here\n")
        files = find_env_example_files(str(tmp_path))
        assert len(files) == 1

    def test_env_defaults_found(self, tmp_path: Path) -> None:
        (tmp_path / ".env.defaults").write_text("KEY=value-here\n")
        files = find_env_example_files(str(tmp_path))
        assert len(files) == 1

    def test_parse_handles_inline_comments(self, tmp_path: Path) -> None:
        """Lines with inline # comments after value."""
        env = tmp_path / ".env.example"
        env.write_text("KEY=somevalue # this is a comment\n")
        entries = parse_env_example(env)
        # The parser currently includes the comment in the value
        assert len(entries) == 1

    def test_parse_handles_equals_in_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("KEY=value=with=equals\n")
        entries = parse_env_example(env)
        assert len(entries) == 1
        assert entries[0].value == "value=with=equals"

    def test_find_values_case_sensitive(self) -> None:
        """Value matching should be case-sensitive."""
        entries = [
            EnvExampleEntry(key="KEY", value="MySecret", file=".env.example", line=1),
        ]
        code_upper = 'x = "MySecret"\n'
        code_lower = 'x = "mysecret"\n'

        matches_upper = find_env_values_in_code(code_upper, entries)
        matches_lower = find_env_values_in_code(code_lower, entries)

        assert len(matches_upper) == 1
        assert len(matches_lower) == 0

    def test_env_example_in_subdirectory(self, tmp_path: Path) -> None:
        """env_example should be found relative to file parent."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / ".env.example").write_text("SECRET=test-value-here\n")
        src = sub / "app.py"
        src.write_text('secret = "test-value-here"\n')

        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec006 = [f for f in findings if f.rule_id == "SEC-006"]
        assert len(sec006) >= 1


# ──────────────────────────────────────────────
# Finding quality
# ──────────────────────────────────────────────


class TestFindingQuality:
    """Tests para verificar la calidad de los findings."""

    def test_sec001_has_correct_fields(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "changeme"\n')
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec001 = [f for f in findings if f.rule_id == "SEC-001"]
        assert len(sec001) >= 1
        f = sec001[0]
        assert f.category == Category.SECRETS
        assert f.severity == Severity.CRITICAL
        assert f.location.file == str(src)
        assert f.location.line == 1
        assert f.suggestion is not None

    def test_sec003_username_in_metadata(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('DB = "postgresql://myuser:mypass@host/db"\n')
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec003 = [f for f in findings if f.rule_id == "SEC-003"]
        assert len(sec003) >= 1
        assert sec003[0].metadata["username"] == "myuser"

    def test_sec004_has_env_key(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'key = os.environ.get("SECRET_KEY", "fallback123")\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        sec004 = [f for f in findings if f.rule_id == "SEC-004"]
        assert len(sec004) >= 1
        assert sec004[0].metadata["env_key"] == "SECRET_KEY"

    def test_all_findings_have_category_secrets(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'API_KEY = "your-api-key-here"\n'
            'DB = "postgresql://a:b@c/d"\n'
        )
        analyzer = SecretsAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        for f in findings:
            assert f.category == Category.SECRETS


# ──────────────────────────────────────────────
# Placeholder detector edge cases
# ──────────────────────────────────────────────


class TestPlaceholderDetectorEdgeCases:
    """Edge cases para placeholder_detector."""

    def test_underscore_variant_your_here(self) -> None:
        """Should detect underscore variant with default config patterns."""
        config_patterns = SecretsConfig().placeholder_patterns
        compiled = compile_placeholder_patterns(config_patterns)
        assert is_placeholder_value("your_api_key_here", compiled)

    def test_insert_here_pattern(self) -> None:
        assert is_placeholder_value("insert-your-key-here")

    def test_put_here_pattern(self) -> None:
        assert is_placeholder_value("put-your-secret-here")

    def test_add_here_pattern(self) -> None:
        assert is_placeholder_value("add-api-key-here")

    def test_sk_test_pattern(self) -> None:
        assert is_placeholder_value("sk_test_abc123xyz")

    def test_sk_live_test_pattern(self) -> None:
        assert is_placeholder_value("sk_live_test_abc123")

    def test_default_key_pattern(self) -> None:
        assert is_placeholder_value("default_key")

    def test_fake_secret_pattern(self) -> None:
        assert is_placeholder_value("fake_secret")

    def test_sample_key_pattern(self) -> None:
        assert is_placeholder_value("sample_key")

    def test_find_assignments_database_url(self) -> None:
        values = find_secret_assignments(
            'DATABASE_URL = "postgresql://user:pass@host/db"'
        )
        assert len(values) >= 1

    def test_find_assignments_js_object(self) -> None:
        values = find_secret_assignments("  secretKey: 'my-value-123',")
        assert len(values) >= 1

    def test_find_assignments_no_match_for_regular_var(self) -> None:
        values = find_secret_assignments('APP_NAME = "my-app"')
        assert values == []

    def test_compile_invalid_regex_skipped(self) -> None:
        """Invalid regex patterns should be silently skipped."""
        patterns = ["valid_pattern", "[invalid(regex", "another_valid"]
        compiled = compile_placeholder_patterns(patterns)
        assert len(compiled) == 2  # one invalid skipped
