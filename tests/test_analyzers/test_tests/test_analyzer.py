"""Tests para TestQualityAnalyzer completo."""

from pathlib import Path

import pytest

from vigil.analyzers.tests.analyzer import TestQualityAnalyzer
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "tests"


class TestTestQualityAnalyzerProtocol:
    """Tests para verificar que TestQualityAnalyzer cumple el protocolo."""

    def test_name(self) -> None:
        analyzer = TestQualityAnalyzer()
        assert analyzer.name == "test-quality"

    def test_category(self) -> None:
        analyzer = TestQualityAnalyzer()
        assert analyzer.category == Category.TEST_QUALITY

    def test_analyze_returns_list(self) -> None:
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        result = analyzer.analyze([], config)
        assert isinstance(result, list)
        assert result == []

    def test_analyze_empty_files(self) -> None:
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        result = analyzer.analyze(["/nonexistent/path.py"], config)
        assert result == []

    def test_not_collected_by_pytest(self) -> None:
        """TestQualityAnalyzer.__test__ = False prevents pytest collection."""
        assert TestQualityAnalyzer.__test__ is False


class TestTestQualityAnalyzerPython:
    """Tests con fixture Python insegura."""

    def test_detects_test_without_assertions(self, tmp_path: Path) -> None:
        """TEST-001: Test sin assertions."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_login():\n"
            "    response = client.post('/login')\n"
            "    # No assertions\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1
        assert "test_login" in test001[0].message
        assert "no assertions" in test001[0].message.lower()

    def test_detects_trivial_assert(self, tmp_path: Path) -> None:
        """TEST-002: Assertion trivial — assert x is not None."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_user_exists():\n"
            "    user = get_user(1)\n"
            "    assert user is not None\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test002 = [f for f in findings if f.rule_id == "TEST-002"]
        assert len(test002) >= 1
        assert "trivial" in test002[0].message.lower()

    def test_detects_catch_all(self, tmp_path: Path) -> None:
        """TEST-003: Catches all exceptions."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_complex():\n"
            "    try:\n"
            "        result = complex_operation()\n"
            "    except Exception:\n"
            "        pass\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test003 = [f for f in findings if f.rule_id == "TEST-003"]
        assert len(test003) == 1
        assert "catches all exceptions" in test003[0].message.lower()

    def test_detects_skip_without_reason(self, tmp_path: Path) -> None:
        """TEST-004: Skip sin justificacion."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "import pytest\n"
            "\n"
            "@pytest.mark.skip\n"
            "def test_broken():\n"
            "    assert 1 + 1 == 2\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test004 = [f for f in findings if f.rule_id == "TEST-004"]
        assert len(test004) == 1
        assert "skip" in test004[0].message.lower()
        assert test004[0].severity == Severity.LOW

    def test_detects_api_test_without_status(self, tmp_path: Path) -> None:
        """TEST-005: API test sin status code assertion."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_api():\n"
            "    response = client.get('/api/users')\n"
            "    data = response.json()\n"
            "    assert len(data) > 0\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test005 = [f for f in findings if f.rule_id == "TEST-005"]
        assert len(test005) == 1
        assert "status code" in test005[0].message.lower()

    def test_detects_mock_mirror(self, tmp_path: Path) -> None:
        """TEST-006: Mock mirror."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_price():\n"
            "    mock_calc.return_value = 42\n"
            "    result = get_price()\n"
            "    assert result == 42\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test006 = [f for f in findings if f.rule_id == "TEST-006"]
        assert len(test006) == 1
        assert "mock" in test006[0].message.lower()
        assert "42" in test006[0].message

    def test_no_findings_on_good_tests(self, tmp_path: Path) -> None:
        """Tests bien escritos no deben generar findings."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "import pytest\n"
            "\n"
            "def test_addition():\n"
            "    result = add(2, 3)\n"
            "    assert result == 5\n"
            "    assert isinstance(result, int)\n"
            "\n"
            "def test_raises():\n"
            "    with pytest.raises(ValueError):\n"
            "        divide(1, 0)\n"
            "\n"
            "@pytest.mark.skip(reason='Requires external service')\n"
            "def test_external():\n"
            "    pass\n"
            "\n"
            "def test_api():\n"
            "    response = client.get('/api')\n"
            "    assert response.status_code == 200\n"
            "    assert response.json()['status'] == 'ok'\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_non_test_file_ignored(self, tmp_path: Path) -> None:
        """Archivos que no son de test deben ignorarse."""
        src = tmp_path / "app.py"
        src.write_text(
            "def compute():\n"
            "    return 42\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_min_assertions_config(self, tmp_path: Path) -> None:
        """min_assertions_per_test debe ser configurable."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_single_assert():\n"
            "    assert add(2, 3) == 5\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.min_assertions_per_test = 2
        findings = analyzer.analyze([str(src)], config)

        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1
        assert "1 assertion" in test001[0].message

    def test_disable_trivial_asserts(self, tmp_path: Path) -> None:
        """detect_trivial_asserts = False debe desactivar TEST-002."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_user_exists():\n"
            "    user = get_user(1)\n"
            "    assert user is not None\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.detect_trivial_asserts = False
        findings = analyzer.analyze([str(src)], config)

        test002 = [f for f in findings if f.rule_id == "TEST-002"]
        assert len(test002) == 0

    def test_disable_mock_mirrors(self, tmp_path: Path) -> None:
        """detect_mock_mirrors = False debe desactivar TEST-006."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_price():\n"
            "    mock_calc.return_value = 42\n"
            "    result = get_price()\n"
            "    assert result == 42\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.detect_mock_mirrors = False
        findings = analyzer.analyze([str(src)], config)

        test006 = [f for f in findings if f.rule_id == "TEST-006"]
        assert len(test006) == 0


class TestTestQualityAnalyzerJavaScript:
    """Tests con archivos JavaScript."""

    def test_detects_js_empty_test(self, tmp_path: Path) -> None:
        """TEST-001: Test sin assertions en JS."""
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('should create user', () => {\n"
            "  const user = createUser('alice');\n"
            "  console.log(user);\n"
            "});\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1

    def test_detects_js_trivial_assert(self, tmp_path: Path) -> None:
        """TEST-002: toBeTruthy() es trivial."""
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('user exists', () => {\n"
            "  const user = getUser(1);\n"
            "  expect(user).toBeTruthy();\n"
            "});\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test002 = [f for f in findings if f.rule_id == "TEST-002"]
        assert len(test002) >= 1

    def test_detects_js_skip(self, tmp_path: Path) -> None:
        """TEST-004: test.skip sin razon."""
        src = tmp_path / "app.test.js"
        src.write_text(
            "test.skip('broken feature', () => {\n"
            "  expect(1 + 1).toBe(2);\n"
            "});\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test004 = [f for f in findings if f.rule_id == "TEST-004"]
        assert len(test004) == 1

    def test_detects_js_mock_mirror(self, tmp_path: Path) -> None:
        """TEST-006: Mock mirror en JS."""
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('price', () => {\n"
            "  const mock = jest.fn().mockReturnValue(42);\n"
            "  const result = mock();\n"
            "  expect(result).toBe(42);\n"
            "});\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test006 = [f for f in findings if f.rule_id == "TEST-006"]
        assert len(test006) == 1

    def test_no_findings_on_good_js_tests(self, tmp_path: Path) -> None:
        """Tests JS bien escritos no deben generar findings."""
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('should add numbers', () => {\n"
            "  const result = add(2, 3);\n"
            "  expect(result).toBe(5);\n"
            "  expect(result).toBeGreaterThan(0);\n"
            "});\n"
            "\n"
            "test('should throw on invalid', () => {\n"
            "  expect(() => divide(1, 0)).toThrow();\n"
            "});\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0


class TestTestQualityAnalyzerEdgeCases:
    """Tests de edge cases."""

    def test_empty_file(self, tmp_path: Path) -> None:
        src = tmp_path / "test_empty.py"
        src.write_text("")

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_file_with_only_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "test_imports.py"
        src.write_text(
            "import pytest\n"
            "import os\n"
            "from pathlib import Path\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_non_utf8_file(self, tmp_path: Path) -> None:
        """Archivos con encoding no-UTF8 no deben crashear."""
        src = tmp_path / "test_encoding.py"
        src.write_bytes(b"def test_x():\n    assert True\n\xff\xfe")

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        # Should not raise

    def test_file_not_found(self) -> None:
        """Archivos inexistentes no deben crashear."""
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze(["/nonexistent/test_x.py"], config)
        assert len(findings) == 0

    def test_conftest_in_tests_dir(self, tmp_path: Path) -> None:
        """conftest.py en un directorio tests/ se considera archivo de test."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        src = tests_dir / "conftest.py"
        src.write_text(
            "import pytest\n"
            "\n"
            "@pytest.fixture\n"
            "def client():\n"
            "    return TestClient(app)\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        # conftest has no test functions, so no TEST-001 findings
        assert len([f for f in findings if f.rule_id == "TEST-001"]) == 0

    def test_finding_metadata(self, tmp_path: Path) -> None:
        """Verificar que los findings tienen metadata correcta."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_empty():\n"
            "    result = compute()\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) >= 1
        finding = findings[0]
        assert finding.rule_id == "TEST-001"
        assert finding.category == Category.TEST_QUALITY
        assert finding.severity == Severity.HIGH
        assert finding.location.file == str(src)
        assert finding.location.line is not None
        assert finding.suggestion is not None
        assert "test_name" in finding.metadata
        assert finding.metadata["test_name"] == "test_empty"

    def test_fixture_integration_python(self) -> None:
        """Test completo con fixture Python insegura."""
        fixture_path = FIXTURES_DIR / "empty_tests_python.py"
        if not fixture_path.exists():
            pytest.skip("Fixture not found")

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(fixture_path)], config)

        # Debe detectar multiples tipos de issues
        rule_ids = {f.rule_id for f in findings}
        assert "TEST-001" in rule_ids  # Empty tests
        assert "TEST-004" in rule_ids  # Skips without reason

    def test_fixture_integration_js(self) -> None:
        """Test completo con fixture JS insegura."""
        fixture_path = FIXTURES_DIR / "empty_tests_js.js"
        if not fixture_path.exists():
            pytest.skip("Fixture not found")

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(fixture_path)], config)

        rule_ids = {f.rule_id for f in findings}
        assert "TEST-001" in rule_ids
        assert "TEST-004" in rule_ids

    def test_fixture_secure_no_findings(self) -> None:
        """Fixture con tests bien escritos no debe generar findings."""
        fixture_path = FIXTURES_DIR / "secure_tests_python.py"
        if not fixture_path.exists():
            pytest.skip("Fixture not found")

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(fixture_path)], config)

        assert len(findings) == 0

    def test_trivial_only_when_all_trivial(self, tmp_path: Path) -> None:
        """TEST-002 solo se reporta si TODAS las assertions son triviales."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_mixed():\n"
            "    user = get_user(1)\n"
            "    assert user is not None\n"
            "    assert user.name == 'alice'\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test002 = [f for f in findings if f.rule_id == "TEST-002"]
        # One trivial + one real assertion → should NOT report TEST-002
        assert len(test002) == 0

    def test_multiple_test_functions_in_one_file(self, tmp_path: Path) -> None:
        """Multiples funciones de test en un archivo — cada una evaluada independientemente."""
        src = tmp_path / "test_multi.py"
        src.write_text(
            "def test_good():\n"
            "    assert add(2, 3) == 5\n"
            "\n"
            "def test_empty():\n"
            "    compute()\n"
            "\n"
            "def test_also_good():\n"
            "    assert subtract(5, 3) == 2\n"
        )

        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1
        assert "test_empty" in test001[0].message
