"""Tests para coverage_heuristics — deteccion de archivos de test."""

from vigil.analyzers.tests.coverage_heuristics import (
    detect_test_framework,
    is_js_test_file,
    is_python_test_file,
    is_test_file,
)


class TestIsTestFile:
    """Tests para is_test_file."""

    def test_python_test_prefix(self) -> None:
        assert is_test_file("test_something.py")
        assert is_test_file("tests/test_auth.py")
        assert is_test_file("/home/user/project/tests/test_engine.py")

    def test_python_test_suffix(self) -> None:
        assert is_test_file("something_test.py")
        assert is_test_file("tests/auth_test.py")

    def test_python_not_test(self) -> None:
        assert not is_test_file("src/auth.py")
        assert not is_test_file("src/utils_helper.py")

    def test_js_test_file(self) -> None:
        assert is_test_file("auth.test.js")
        assert is_test_file("__tests__/auth.test.ts")
        assert is_test_file("src/components/Button.spec.tsx")

    def test_js_not_test(self) -> None:
        assert not is_test_file("src/auth.js")
        assert not is_test_file("src/utils.ts")

    def test_in_test_directory(self) -> None:
        assert is_test_file("tests/helpers.py")
        assert is_test_file("test/utils.py")
        assert is_test_file("__tests__/helpers.js")

    def test_windows_paths(self) -> None:
        assert is_test_file("tests\\test_auth.py")
        assert is_test_file("tests\\helpers.py")


class TestIsPythonTestFile:
    """Tests para is_python_test_file."""

    def test_python_test(self) -> None:
        assert is_python_test_file("test_auth.py")
        assert is_python_test_file("tests/test_engine.py")

    def test_not_python(self) -> None:
        assert not is_python_test_file("auth.test.js")
        assert not is_python_test_file("src/auth.py")


class TestIsJsTestFile:
    """Tests para is_js_test_file."""

    def test_js_test(self) -> None:
        assert is_js_test_file("auth.test.js")
        assert is_js_test_file("auth.spec.ts")

    def test_not_js(self) -> None:
        assert not is_js_test_file("test_auth.py")
        assert not is_js_test_file("src/auth.js")

    def test_tsx_test(self) -> None:
        assert is_js_test_file("Component.test.tsx")
        assert is_js_test_file("Component.spec.tsx")


class TestDetectTestFramework:
    """Tests para detect_test_framework."""

    def test_pytest_import(self) -> None:
        content = "import pytest\n\ndef test_x():\n    assert True\n"
        assert detect_test_framework(content, is_python=True) == "pytest"

    def test_pytest_from_import(self) -> None:
        content = "from pytest import raises\n\ndef test_x():\n    pass\n"
        assert detect_test_framework(content, is_python=True) == "pytest"

    def test_unittest_import(self) -> None:
        content = "import unittest\n\nclass TestX(unittest.TestCase):\n    pass\n"
        assert detect_test_framework(content, is_python=True) == "unittest"

    def test_pytest_convention(self) -> None:
        content = "def test_something():\n    assert 1 == 1\n"
        assert detect_test_framework(content, is_python=True) == "pytest"

    def test_jest(self) -> None:
        content = "test('x', () => {\n  expect(1).toBe(1);\n});\n"
        assert detect_test_framework(content, is_python=False) == "jest"

    def test_mocha(self) -> None:
        content = "describe('x', () => {\n  it('y', () => {\n    assert(true);\n  });\n});\n"
        assert detect_test_framework(content, is_python=False) == "mocha"

    def test_unknown(self) -> None:
        content = "function helper() { return 42; }\n"
        assert detect_test_framework(content, is_python=False) is None

    def test_empty_content(self) -> None:
        assert detect_test_framework("", is_python=True) is None
