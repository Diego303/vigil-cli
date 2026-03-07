"""Tests para placeholder_detector."""

import pytest

from vigil.analyzers.secrets.placeholder_detector import (
    compile_placeholder_patterns,
    find_secret_assignments,
    is_placeholder_value,
)


class TestIsPlaceholderValue:
    """Tests para deteccion de valores placeholder."""

    def test_changeme(self) -> None:
        assert is_placeholder_value("changeme") is True

    def test_your_key_here(self) -> None:
        assert is_placeholder_value("your-api-key-here") is True

    def test_todo(self) -> None:
        assert is_placeholder_value("TODO_replace_this") is True

    def test_fixme(self) -> None:
        assert is_placeholder_value("FIXME_set_real_value") is True

    def test_xxx(self) -> None:
        assert is_placeholder_value("xxxx") is True

    def test_sk_your(self) -> None:
        assert is_placeholder_value("sk-your-api-key") is True

    def test_pk_test(self) -> None:
        assert is_placeholder_value("pk_test_abc123") is True

    def test_secret123(self) -> None:
        assert is_placeholder_value("secret123") is True

    def test_supersecret(self) -> None:
        assert is_placeholder_value("supersecret") is True

    def test_example_com(self) -> None:
        assert is_placeholder_value("admin@example.com") is True

    def test_real_value_not_placeholder(self) -> None:
        assert is_placeholder_value("sk_live_a3f8b2c1d9e0x7y4z") is False

    def test_random_string_not_placeholder(self) -> None:
        assert is_placeholder_value("x7q2m9p4k1") is False

    def test_empty_not_placeholder(self) -> None:
        assert is_placeholder_value("") is False

    def test_custom_patterns(self) -> None:
        import re

        patterns = [re.compile(r"MY_CUSTOM_PLACEHOLDER", re.IGNORECASE)]
        assert is_placeholder_value("MY_CUSTOM_PLACEHOLDER", patterns) is True
        assert is_placeholder_value("something_else", patterns) is False

    def test_replace_me(self) -> None:
        assert is_placeholder_value("replaceme") is True

    def test_placeholder(self) -> None:
        assert is_placeholder_value("placeholder_value") is True


class TestFindSecretAssignments:
    """Tests para deteccion de asignaciones de secrets."""

    def test_python_secret_key(self) -> None:
        values = find_secret_assignments('SECRET_KEY = "mysecret123"')
        assert "mysecret123" in values

    def test_python_api_key(self) -> None:
        values = find_secret_assignments('API_KEY = "abc123def456"')
        assert "abc123def456" in values

    def test_python_password(self) -> None:
        values = find_secret_assignments('PASSWORD = "admin123"')
        assert "admin123" in values

    def test_js_const_secret(self) -> None:
        values = find_secret_assignments("const secretKey = 'mysecret';")
        assert "mysecret" in values

    def test_js_let_password(self) -> None:
        values = find_secret_assignments("let password = 'admin123';")
        assert "admin123" in values

    def test_object_property(self) -> None:
        values = find_secret_assignments("  password: 'mypass123',")
        assert "mypass123" in values

    def test_no_secret(self) -> None:
        values = find_secret_assignments('APP_NAME = "my-app"')
        assert values == []

    def test_short_value_excluded(self) -> None:
        values = find_secret_assignments('PASSWORD = "ab"')
        assert values == []

    def test_database_url(self) -> None:
        values = find_secret_assignments('DATABASE_URL = "postgresql://user:pass@host/db"')
        assert len(values) >= 1
