"""QA regression tests for FASE 3 — TestQualityAnalyzer.

Covers:
1. Regression tests for each bug found during QA audit
2. Edge cases: async functions, single-line tests, deeply nested classes
3. False positive tests (legitimate code should NOT trigger findings)
4. False negative tests (bad code MUST trigger findings)
5. Configuration tests
6. Integration tests with fixtures
7. Boundary conditions
"""

from pathlib import Path

import pytest

from vigil.analyzers.tests.analyzer import TestQualityAnalyzer, _is_skipped_test
from vigil.analyzers.tests.assert_checker import (
    count_assertions,
    extract_js_test_functions,
    extract_python_test_functions,
    find_catch_all_exceptions,
    find_skips_without_reason,
    find_trivial_assertions,
    has_status_code_assertion,
    is_api_test,
)
from vigil.analyzers.tests.mock_checker import (
    _is_literal,
    _normalize_value,
    find_assert_values,
    find_mock_mirrors,
    find_mock_return_values,
)
from vigil.analyzers.tests.coverage_heuristics import (
    is_test_file,
    is_python_test_file,
    is_js_test_file,
)
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "tests"


# ──────────────────────────────────────────────
# 1. Regression tests for QA-discovered bugs
# ──────────────────────────────────────────────


class TestRegressionAsyncTestFunctions:
    """BUG-001: async def test_* was not matched by regex."""

    def test_async_test_extracted(self) -> None:
        lines = [
            "async def test_fetch():",
            "    result = await fetch()",
            "    assert result.ok",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "test_fetch"

    def test_async_test_counted_assertions(self) -> None:
        lines = [
            "async def test_fetch():",
            "    result = await fetch()",
            "    assert result.ok",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        _, start, end = funcs[0]
        count = count_assertions(lines, start, end, is_python=True)
        assert count == 1

    def test_async_test_no_assertions_detected(self, tmp_path: Path) -> None:
        """Async test without assertions triggers TEST-001."""
        src = tmp_path / "test_async.py"
        src.write_text(
            "async def test_empty_async():\n"
            "    result = await fetch()\n"
            "    print(result)\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1
        assert "test_empty_async" in test001[0].message

    def test_async_with_self_in_class(self) -> None:
        lines = [
            "class TestAsync:",
            "    async def test_method(self):",
            "        result = await self.client.get('/')",
            "        assert result.status == 200",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "test_method"

    def test_mixed_sync_and_async(self) -> None:
        lines = [
            "def test_sync():",
            "    assert True",
            "",
            "async def test_async():",
            "    result = await get()",
            "    assert result",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 2
        assert funcs[0][0] == "test_sync"
        assert funcs[1][0] == "test_async"


class TestRegressionSingleLineTestFunctions:
    """BUG-002: def test_x(): assert True had 0 assertions."""

    def test_single_line_assertion_counted(self) -> None:
        lines = [
            "def test_one_liner(): assert 1 == 1",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        count = count_assertions(lines, start, end, is_python=True)
        assert count == 1

    def test_single_line_trivial_not_detected_inline(self) -> None:
        """Single-line `def test_x(): assert True` — trivial regex does not match
        the inline form because the line starts with 'def'. This is a known
        limitation; the assertion IS counted, but trivial detection only works
        on standalone assertion lines."""
        lines = [
            "def test_trivial(): assert True",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        # Assertion is counted (BUG-002 fix)
        count = count_assertions(lines, start, end, is_python=True)
        assert count == 1
        # But trivial detection doesn't match inline form (known limitation)
        trivials = find_trivial_assertions(lines, start, end, is_python=True)
        assert len(trivials) == 0

    def test_single_line_no_false_positive(self, tmp_path: Path) -> None:
        """Single-line test with real assertion should NOT trigger TEST-001."""
        src = tmp_path / "test_one.py"
        src.write_text("def test_x(): assert add(2, 3) == 5\n")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 0

    def test_single_line_followed_by_normal_test(self) -> None:
        """Single-line test followed by multi-line test — both extracted."""
        lines = [
            "def test_one(): assert 1 == 1",
            "",
            "def test_two():",
            "    assert 2 == 2",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 2
        # Both should have assertions
        for _, start, end in funcs:
            assert count_assertions(lines, start, end, is_python=True) >= 1

    def test_single_line_with_colon_in_string(self) -> None:
        """Edge: def test_x(): assert msg == 'a:b' — colon in string."""
        lines = [
            "def test_colon(): assert parse('a:b') == ('a', 'b')",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        count = count_assertions(lines, start, end, is_python=True)
        assert count == 1


class TestRegressionBaseExceptionCatch:
    """BUG-003: except BaseException was not detected as catch-all."""

    def test_base_exception_detected(self) -> None:
        lines = [
            "def test_x():",
            "    try:",
            "        op()",
            "    except BaseException:",
            "        pass",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 1

    def test_base_exception_as_var_detected(self) -> None:
        lines = [
            "def test_x():",
            "    try:",
            "        op()",
            "    except BaseException as e:",
            "        pass",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 1

    def test_base_exception_with_raise_not_detected(self) -> None:
        lines = [
            "def test_x():",
            "    try:",
            "        op()",
            "    except BaseException as e:",
            "        raise",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 0


class TestRegressionLiteralQuoteMismatch:
    """BUG-004: _is_literal('hello\") returned True with mismatched quotes."""

    def test_mismatched_quotes_not_literal(self) -> None:
        assert not _is_literal("'hello\"")
        assert not _is_literal("\"hello'")

    def test_matched_quotes_literal(self) -> None:
        assert _is_literal("'hello'")
        assert _is_literal('"hello"')

    def test_empty_string_literal(self) -> None:
        assert _is_literal("''")
        assert _is_literal('""')


# ──────────────────────────────────────────────
# 2. Edge case tests
# ──────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases that could cause crashes or incorrect results."""

    def test_file_with_no_newline_at_end(self, tmp_path: Path) -> None:
        src = tmp_path / "test_no_newline.py"
        src.write_text("def test_x():\n    assert 1 == 1")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-001" for f in findings)

    def test_test_with_only_pass(self, tmp_path: Path) -> None:
        """Test with only 'pass' triggers TEST-001."""
        src = tmp_path / "test_pass.py"
        src.write_text("def test_nothing():\n    pass\n")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1

    def test_test_with_only_docstring(self, tmp_path: Path) -> None:
        """Test with only a docstring triggers TEST-001."""
        src = tmp_path / "test_doc.py"
        src.write_text(
            'def test_placeholder():\n'
            '    """TODO: implement this test."""\n'
            '    pass\n'
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1

    def test_deeply_nested_class_methods(self) -> None:
        lines = [
            "class TestOuter:",
            "    class TestInner:",
            "        def test_deep(self):",
            "            assert deep() == 42",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "test_deep"

    def test_test_function_at_end_of_file_no_trailing_newline(self) -> None:
        lines = [
            "def test_last():",
            "    assert compute() == 1",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        count = count_assertions(lines, start, end, is_python=True)
        assert count == 1

    def test_empty_lines_between_tests(self) -> None:
        lines = [
            "def test_first():",
            "    assert 1 == 1",
            "",
            "",
            "",
            "def test_second():",
            "    assert 2 == 2",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 2

    def test_js_test_with_nested_braces(self) -> None:
        """Nested braces should not confuse the JS brace counter."""
        lines = [
            "test('nested objects', () => {",
            "  const obj = { a: { b: { c: 1 } } };",
            "  expect(obj.a.b.c).toBe(1);",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        count = count_assertions(lines, start, end, is_python=False)
        assert count == 1

    def test_js_test_with_string_containing_braces(self) -> None:
        """Braces inside strings should still be counted (known limitation)."""
        lines = [
            "test('json test', () => {",
            "  const json = '{\"key\": \"value\"}';",
            "  expect(parse(json)).toEqual({key: 'value'});",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        # May not extract correctly due to brace-in-string, but should not crash
        assert isinstance(funcs, list)

    def test_very_long_test_function(self) -> None:
        """Test function with 100 lines — should still extract correctly."""
        lines = ["def test_big():"]
        for i in range(100):
            lines.append(f"    x_{i} = compute({i})")
        lines.append("    assert x_99 == 99")
        lines.append("")

        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        count = count_assertions(lines, start, end, is_python=True)
        assert count == 1

    def test_multiple_test_files(self, tmp_path: Path) -> None:
        """Analyzer processes multiple files in one call."""
        f1 = tmp_path / "test_a.py"
        f2 = tmp_path / "test_b.py"
        f1.write_text("def test_a():\n    pass\n")
        f2.write_text("def test_b():\n    pass\n")

        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(f1), str(f2)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 2
        names = {f.metadata["test_name"] for f in test001}
        assert names == {"test_a", "test_b"}

    def test_binary_file_does_not_crash(self, tmp_path: Path) -> None:
        """Binary file in test dir should not crash analyzer."""
        src = tmp_path / "test_binary.py"
        src.write_bytes(b"\x00\x01\x02\xff\xfe\x80" * 100)
        analyzer = TestQualityAnalyzer()
        # Should not raise
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert isinstance(findings, list)


# ──────────────────────────────────────────────
# 3. False positive tests (should NOT trigger)
# ──────────────────────────────────────────────


class TestFalsePositives:
    """Legitimate code that should NOT generate findings."""

    def test_pytest_raises_counts_as_assertion(self, tmp_path: Path) -> None:
        src = tmp_path / "test_raises.py"
        src.write_text(
            "import pytest\n\n"
            "def test_division_error():\n"
            "    with pytest.raises(ZeroDivisionError):\n"
            "        1 / 0\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-001" for f in findings)

    def test_pytest_warns_counts_as_assertion(self, tmp_path: Path) -> None:
        src = tmp_path / "test_warns.py"
        src.write_text(
            "import pytest\n\n"
            "def test_deprecation():\n"
            "    with pytest.warns(DeprecationWarning):\n"
            "        deprecated_func()\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-001" for f in findings)

    def test_pytest_approx_counts_as_assertion(self, tmp_path: Path) -> None:
        src = tmp_path / "test_approx.py"
        src.write_text(
            "import pytest\n\n"
            "def test_float():\n"
            "    assert compute() == pytest.approx(3.14)\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-001" for f in findings)

    def test_specific_except_not_catch_all(self, tmp_path: Path) -> None:
        """except ValueError is specific, not catch-all."""
        src = tmp_path / "test_specific.py"
        src.write_text(
            "def test_specific_error():\n"
            "    try:\n"
            "        int('abc')\n"
            "    except ValueError:\n"
            "        pass\n"
            "    assert True\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-003" for f in findings)

    def test_skip_with_reason_not_reported(self, tmp_path: Path) -> None:
        src = tmp_path / "test_skip.py"
        src.write_text(
            "import pytest\n\n"
            "@pytest.mark.skip(reason='WIP: needs database')\n"
            "def test_db():\n"
            "    pass\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-004" for f in findings)

    def test_api_test_with_status_code_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "test_api.py"
        src.write_text(
            "def test_api():\n"
            "    response = client.get('/api/users')\n"
            "    assert response.status_code == 200\n"
            "    data = response.json()\n"
            "    assert len(data) > 0\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-005" for f in findings)

    def test_mixed_trivial_and_real_no_test002(self, tmp_path: Path) -> None:
        """Mix of trivial + real assertions → NOT reported as TEST-002."""
        src = tmp_path / "test_mixed.py"
        src.write_text(
            "def test_user():\n"
            "    user = get_user(1)\n"
            "    assert user is not None\n"
            "    assert user.email == 'alice@test.com'\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-002" for f in findings)

    def test_mock_with_different_value_no_mirror(self, tmp_path: Path) -> None:
        """Mock returns 10, assert checks 20 → NOT a mirror."""
        src = tmp_path / "test_nomirror.py"
        src.write_text(
            "def test_transform():\n"
            "    mock_data.return_value = 10\n"
            "    result = transform()\n"
            "    assert result == 20\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert not any(f.rule_id == "TEST-006" for f in findings)

    def test_helper_function_not_flagged(self, tmp_path: Path) -> None:
        """Helper function (not test_*) in test file should not be flagged."""
        src = tmp_path / "test_app.py"
        src.write_text(
            "def make_user(name):\n"
            "    return {'name': name}\n"
            "\n"
            "def test_user():\n"
            "    user = make_user('alice')\n"
            "    assert user['name'] == 'alice'\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert len(findings) == 0

    def test_non_test_file_ignored(self, tmp_path: Path) -> None:
        """Regular Python file should produce zero findings."""
        src = tmp_path / "app.py"
        src.write_text("def compute():\n    return 42\n")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert len(findings) == 0

    def test_js_proper_test_no_findings(self, tmp_path: Path) -> None:
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('adds numbers', () => {\n"
            "  expect(add(1, 2)).toBe(3);\n"
            "  expect(add(-1, 1)).toBe(0);\n"
            "});\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert len(findings) == 0

    def test_skipped_test_body_not_analyzed(self, tmp_path: Path) -> None:
        """Skipped test should not trigger TEST-001 for its body."""
        src = tmp_path / "test_skip_body.py"
        src.write_text(
            "import pytest\n\n"
            "@pytest.mark.skip\n"
            "def test_skipped():\n"
            "    pass\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        # Should get TEST-004 (skip without reason) but NOT TEST-001
        assert not any(f.rule_id == "TEST-001" for f in findings)
        assert any(f.rule_id == "TEST-004" for f in findings)


# ──────────────────────────────────────────────
# 4. False negative tests (MUST trigger findings)
# ──────────────────────────────────────────────


class TestFalseNegatives:
    """Bad code that MUST generate findings."""

    def test_all_trivial_assertions_trigger_test002(self, tmp_path: Path) -> None:
        src = tmp_path / "test_trivial.py"
        src.write_text(
            "def test_all_trivial():\n"
            "    x = get_value()\n"
            "    assert x\n"
            "    assert x is not None\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test002 = [f for f in findings if f.rule_id == "TEST-002"]
        assert len(test002) >= 1

    def test_bare_except_triggers_test003(self, tmp_path: Path) -> None:
        src = tmp_path / "test_bare.py"
        src.write_text(
            "def test_bare_except():\n"
            "    try:\n"
            "        op()\n"
            "    except:\n"
            "        pass\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test003 = [f for f in findings if f.rule_id == "TEST-003"]
        assert len(test003) == 1

    def test_unittest_skip_no_reason_triggers(self, tmp_path: Path) -> None:
        src = tmp_path / "test_unskip.py"
        src.write_text(
            "import unittest\n\n"
            "@unittest.skip\n"
            "def test_skipped():\n"
            "    pass\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test004 = [f for f in findings if f.rule_id == "TEST-004"]
        assert len(test004) == 1

    def test_api_test_without_status_triggers(self, tmp_path: Path) -> None:
        src = tmp_path / "test_nostat.py"
        src.write_text(
            "def test_api_no_status():\n"
            "    response = client.post('/api/data', json={})\n"
            "    data = response.json()\n"
            "    assert data['id'] is not None\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test005 = [f for f in findings if f.rule_id == "TEST-005"]
        assert len(test005) == 1

    def test_mock_mirror_with_string_triggers(self, tmp_path: Path) -> None:
        src = tmp_path / "test_strmirror.py"
        src.write_text(
            "def test_str_mirror():\n"
            '    mock_svc.return_value = "hello"\n'
            "    result = svc.get_greeting()\n"
            '    assert result == "hello"\n'
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test006 = [f for f in findings if f.rule_id == "TEST-006"]
        assert len(test006) == 1

    def test_js_empty_test_triggers(self, tmp_path: Path) -> None:
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('does nothing', () => {\n"
            "  const x = compute();\n"
            "  console.log(x);\n"
            "});\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1

    def test_js_catch_all_triggers(self, tmp_path: Path) -> None:
        src = tmp_path / "app.test.js"
        src.write_text(
            "test('catches everything', () => {\n"
            "  try {\n"
            "    dangerousOp();\n"
            "  } catch(e) {\n"
            "    console.log(e);\n"
            "  }\n"
            "  expect(true).toBe(true);\n"
            "});\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test003 = [f for f in findings if f.rule_id == "TEST-003"]
        assert len(test003) == 1


# ──────────────────────────────────────────────
# 5. Configuration tests
# ──────────────────────────────────────────────


class TestConfigurationBehavior:
    """Test that config flags correctly control behavior."""

    def test_min_assertions_default_is_1(self) -> None:
        config = ScanConfig()
        assert config.tests.min_assertions_per_test == 1

    def test_min_assertions_2_flags_single_assert(self, tmp_path: Path) -> None:
        src = tmp_path / "test_min.py"
        src.write_text(
            "def test_one():\n"
            "    assert compute() == 42\n"
        )
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.min_assertions_per_test = 2
        findings = analyzer.analyze([str(src)], config)
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 1
        assert "1 assertion" in test001[0].message
        assert test001[0].metadata["min_required"] == 2

    def test_min_assertions_2_no_flag_when_2(self, tmp_path: Path) -> None:
        src = tmp_path / "test_min2.py"
        src.write_text(
            "def test_two():\n"
            "    assert compute() == 42\n"
            "    assert isinstance(compute(), int)\n"
        )
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.min_assertions_per_test = 2
        findings = analyzer.analyze([str(src)], config)
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) == 0

    def test_detect_trivial_asserts_false(self, tmp_path: Path) -> None:
        src = tmp_path / "test_notrivial.py"
        src.write_text(
            "def test_x():\n"
            "    assert result is not None\n"
        )
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.detect_trivial_asserts = False
        findings = analyzer.analyze([str(src)], config)
        assert not any(f.rule_id == "TEST-002" for f in findings)

    def test_detect_mock_mirrors_false(self, tmp_path: Path) -> None:
        src = tmp_path / "test_nomock.py"
        src.write_text(
            "def test_mirror():\n"
            "    mock_x.return_value = 42\n"
            "    assert func() == 42\n"
        )
        analyzer = TestQualityAnalyzer()
        config = ScanConfig()
        config.tests.detect_mock_mirrors = False
        findings = analyzer.analyze([str(src)], config)
        assert not any(f.rule_id == "TEST-006" for f in findings)


# ──────────────────────────────────────────────
# 6. Integration tests with fixture files
# ──────────────────────────────────────────────


class TestFixtureIntegration:
    """Integration tests using fixture files."""

    def test_edge_cases_python_fixture(self) -> None:
        fixture = FIXTURES_DIR / "edge_cases_python.py"
        if not fixture.exists():
            pytest.skip("Edge cases fixture not found")

        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(fixture)], ScanConfig())

        # Async empty test should trigger TEST-001
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        names_001 = {f.metadata.get("test_name") for f in test001}
        assert "test_async_empty" in names_001

        # BaseException catch-all should trigger TEST-003
        test003 = [f for f in findings if f.rule_id == "TEST-003"]
        assert len(test003) >= 1

        # Direct mock mirror should trigger TEST-006
        test006 = [f for f in findings if f.rule_id == "TEST-006"]
        assert len(test006) >= 1

        # Parametrized test with real assertions should NOT trigger
        assert not any(
            f.metadata.get("test_name") == "test_parametrized_add"
            and f.rule_id == "TEST-001"
            for f in findings
        )

    def test_edge_cases_js_fixture(self) -> None:
        fixture = FIXTURES_DIR / "edge_cases_js.js"
        if not fixture.exists():
            pytest.skip("Edge cases JS fixture not found")

        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(fixture)], ScanConfig())

        # Async empty test triggers TEST-001
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert len(test001) >= 1

        # it.skip and xtest trigger TEST-004
        test004 = [f for f in findings if f.rule_id == "TEST-004"]
        assert len(test004) >= 2

    def test_npm_fixture(self) -> None:
        fixture = FIXTURES_DIR / "npm_tests.test.js"
        if not fixture.exists():
            pytest.skip("npm fixture not found")

        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(fixture)], ScanConfig())

        rule_ids = {f.rule_id for f in findings}
        assert "TEST-001" in rule_ids  # deleteUser test
        assert "TEST-006" in rule_ids  # mock mirror

    def test_secure_python_fixture_clean(self) -> None:
        fixture = FIXTURES_DIR / "secure_tests_python.py"
        if not fixture.exists():
            pytest.skip("Secure fixture not found")

        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(fixture)], ScanConfig())
        assert len(findings) == 0

    def test_empty_python_fixture_all_rules(self) -> None:
        """The empty_tests_python fixture should trigger multiple rule types."""
        fixture = FIXTURES_DIR / "empty_tests_python.py"
        if not fixture.exists():
            pytest.skip("Fixture not found")

        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(fixture)], ScanConfig())

        rule_ids = {f.rule_id for f in findings}
        assert "TEST-001" in rule_ids
        assert "TEST-002" in rule_ids
        assert "TEST-003" in rule_ids
        assert "TEST-004" in rule_ids
        assert "TEST-005" in rule_ids
        assert "TEST-006" in rule_ids


# ──────────────────────────────────────────────
# 7. Boundary condition tests
# ──────────────────────────────────────────────


class TestBoundaryConditions:
    """Boundary condition tests for assert_checker and mock_checker."""

    def test_count_assertions_out_of_bounds_range(self) -> None:
        """Range extending beyond file length should not crash."""
        lines = ["def test_x():", "    assert True"]
        count = count_assertions(lines, 1, 1000, is_python=True)
        assert count == 1

    def test_find_trivial_out_of_bounds(self) -> None:
        lines = ["def test_x():", "    assert True"]
        results = find_trivial_assertions(lines, 1, 1000, is_python=True)
        assert len(results) == 1

    def test_find_catch_all_out_of_bounds(self) -> None:
        lines = ["def test_x():", "    try:", "        op()", "    except:", "        pass"]
        results = find_catch_all_exceptions(lines, 1, 1000, is_python=True)
        assert len(results) == 1

    def test_start_equals_end_returns_nothing(self) -> None:
        lines = ["def test_x():", "    assert True"]
        assert count_assertions(lines, 1, 1, is_python=True) == 0
        assert find_trivial_assertions(lines, 1, 1, is_python=True) == []
        assert find_catch_all_exceptions(lines, 1, 1, is_python=True) == []

    def test_start_greater_than_end_returns_nothing(self) -> None:
        lines = ["def test_x():", "    assert True"]
        assert count_assertions(lines, 5, 1, is_python=True) == 0

    def test_empty_lines_list(self) -> None:
        assert count_assertions([], 0, 0, is_python=True) == 0
        assert find_trivial_assertions([], 0, 0, is_python=True) == []
        assert find_mock_return_values([], 0, 0, is_python=True) == []
        assert find_assert_values([], 0, 0, is_python=True) == []

    def test_normalize_value_edge_cases(self) -> None:
        assert _normalize_value("  42  ") == "42"
        assert _normalize_value("True") == "true"
        assert _normalize_value("FALSE") == "false"
        assert _normalize_value("None") == "null"
        assert _normalize_value("null") == "null"
        assert _normalize_value("undefined") == "null"
        assert _normalize_value("'hello world'") == "hello world"
        assert _normalize_value('"hello world"') == "hello world"

    def test_is_literal_various_types(self) -> None:
        # Numbers
        assert _is_literal("42")
        assert _is_literal("-1")
        assert _is_literal("3.14")
        assert _is_literal("-0.5")
        # Strings
        assert _is_literal("'hello'")
        assert _is_literal('"hello"')
        # Booleans
        assert _is_literal("True")
        assert _is_literal("False")
        assert _is_literal("true")
        assert _is_literal("false")
        # None/null
        assert _is_literal("None")
        assert _is_literal("null")
        assert _is_literal("undefined")
        # Empty containers
        assert _is_literal("{}")
        assert _is_literal("[]")
        # NOT literals
        assert not _is_literal("some_variable")
        assert not _is_literal("func()")
        assert not _is_literal("[1, 2, 3]")
        assert not _is_literal("{'a': 1}")

    def test_is_skipped_test_boundary(self) -> None:
        """_is_skipped_test at the very start of file."""
        lines = [
            "@pytest.mark.skip",
            "def test_first():",
            "    pass",
        ]
        assert _is_skipped_test(lines, 2, is_python=True)

    def test_is_skipped_test_not_skipped(self) -> None:
        lines = [
            "def test_normal():",
            "    assert True",
        ]
        assert not _is_skipped_test(lines, 1, is_python=True)


# ──────────────────────────────────────────────
# 8. Coverage heuristics edge cases
# ──────────────────────────────────────────────


class TestCoverageHeuristicsEdge:
    """Edge cases for file identification."""

    def test_conftest_in_tests_dir(self) -> None:
        assert is_test_file("tests/conftest.py")
        assert is_python_test_file("tests/conftest.py")

    def test_helper_in_tests_dir(self) -> None:
        assert is_test_file("tests/helpers.py")

    def test_non_test_js_file(self) -> None:
        assert not is_js_test_file("src/utils.js")
        assert not is_js_test_file("lib/helper.ts")

    def test_mjs_test_file(self) -> None:
        assert is_js_test_file("auth.test.mjs")

    def test_cjs_test_file(self) -> None:
        assert is_js_test_file("auth.spec.cjs")

    def test_deeply_nested_path(self) -> None:
        assert is_test_file("project/src/tests/unit/test_auth.py")

    def test_test_dir_but_not_py_or_js(self) -> None:
        """File in tests/ but not .py or .js — is_test_file True, but not python/js."""
        assert is_test_file("tests/data.txt")
        assert not is_python_test_file("tests/data.txt")
        assert not is_js_test_file("tests/data.txt")

    def test_spec_directory(self) -> None:
        assert is_test_file("spec/helper.rb")
        assert is_test_file("specs/some_test.py")


# ──────────────────────────────────────────────
# 9. Finding structure validation
# ──────────────────────────────────────────────


class TestFindingStructure:
    """Verify all findings have correct structure per CLAUDE.md requirements."""

    def test_finding_has_all_required_fields(self, tmp_path: Path) -> None:
        src = tmp_path / "test_app.py"
        src.write_text(
            "def test_empty():\n"
            "    compute()\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        assert len(findings) >= 1

        for finding in findings:
            # rule_id format
            assert finding.rule_id.startswith("TEST-")
            assert len(finding.rule_id) == 8  # TEST-NNN
            # category
            assert finding.category == Category.TEST_QUALITY
            # severity is a valid enum
            assert finding.severity in list(Severity)
            # message is actionable (not empty)
            assert len(finding.message) > 10
            # location has file
            assert finding.location.file == str(src)
            # suggestion is concrete
            assert finding.suggestion is not None
            assert len(finding.suggestion) > 10

    def test_test001_severity_high(self, tmp_path: Path) -> None:
        src = tmp_path / "test_sev.py"
        src.write_text("def test_x():\n    pass\n")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test001 = [f for f in findings if f.rule_id == "TEST-001"]
        assert all(f.severity == Severity.HIGH for f in test001)

    def test_test002_severity_medium(self, tmp_path: Path) -> None:
        src = tmp_path / "test_sev2.py"
        src.write_text("def test_x():\n    assert True\n")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test002 = [f for f in findings if f.rule_id == "TEST-002"]
        assert all(f.severity == Severity.MEDIUM for f in test002)

    def test_test004_severity_low(self, tmp_path: Path) -> None:
        src = tmp_path / "test_sev4.py"
        src.write_text("import pytest\n\n@pytest.mark.skip\ndef test_x():\n    pass\n")
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test004 = [f for f in findings if f.rule_id == "TEST-004"]
        assert all(f.severity == Severity.LOW for f in test004)

    def test_test003_severity_medium(self, tmp_path: Path) -> None:
        src = tmp_path / "test_sev3.py"
        src.write_text(
            "def test_x():\n"
            "    try:\n"
            "        op()\n"
            "    except Exception:\n"
            "        pass\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test003 = [f for f in findings if f.rule_id == "TEST-003"]
        assert all(f.severity == Severity.MEDIUM for f in test003)

    def test_test005_severity_medium(self, tmp_path: Path) -> None:
        src = tmp_path / "test_sev5.py"
        src.write_text(
            "def test_api():\n"
            "    response = client.get('/api')\n"
            "    assert len(response.json()) > 0\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test005 = [f for f in findings if f.rule_id == "TEST-005"]
        assert all(f.severity == Severity.MEDIUM for f in test005)

    def test_test006_severity_medium(self, tmp_path: Path) -> None:
        src = tmp_path / "test_sev6.py"
        src.write_text(
            "def test_x():\n"
            "    mock.return_value = 42\n"
            "    assert func() == 42\n"
        )
        analyzer = TestQualityAnalyzer()
        findings = analyzer.analyze([str(src)], ScanConfig())
        test006 = [f for f in findings if f.rule_id == "TEST-006"]
        assert all(f.severity == Severity.MEDIUM for f in test006)
