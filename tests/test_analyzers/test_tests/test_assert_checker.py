"""Tests para assert_checker — deteccion de assertions en tests."""

import pytest

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


class TestExtractPythonTestFunctions:
    """Tests para extract_python_test_functions."""

    def test_simple_test_function(self) -> None:
        lines = [
            "def test_something():",
            "    result = compute()",
            "    assert result == 42",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        name, start, end = funcs[0]
        assert name == "test_something"
        assert start == 1  # 1-based line number of the def
        assert end >= 3

    def test_multiple_test_functions(self) -> None:
        lines = [
            "def test_first():",
            "    assert True",
            "",
            "def test_second():",
            "    assert False",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 2
        assert funcs[0][0] == "test_first"
        assert funcs[1][0] == "test_second"

    def test_indented_test_methods(self) -> None:
        lines = [
            "class TestSomething:",
            "    def test_method(self):",
            "        assert 1 == 1",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "test_method"

    def test_no_test_functions(self) -> None:
        lines = [
            "def helper_function():",
            "    return 42",
            "",
            "def another_helper():",
            "    pass",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 0

    def test_empty_file(self) -> None:
        funcs = extract_python_test_functions([])
        assert len(funcs) == 0

    def test_test_with_decorators(self) -> None:
        """Decoradores no se capturan como parte del test, solo el def."""
        lines = [
            "@pytest.mark.slow",
            "def test_decorated():",
            "    assert True",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "test_decorated"

    def test_multiline_body(self) -> None:
        lines = [
            "def test_complex():",
            "    a = 1",
            "    b = 2",
            "    c = a + b",
            "    assert c == 3",
            "    assert c > 0",
            "",
        ]
        funcs = extract_python_test_functions(lines)
        assert len(funcs) == 1
        _, start, end = funcs[0]
        # El cuerpo debe incluir todas las lineas con indentacion
        assert end >= 6  # Al menos hasta la linea 6 (assert c > 0)


class TestExtractJsTestFunctions:
    """Tests para extract_js_test_functions."""

    def test_jest_test(self) -> None:
        lines = [
            "test('should work', () => {",
            "  const result = compute();",
            "  expect(result).toBe(42);",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "should work"

    def test_mocha_it(self) -> None:
        lines = [
            "it('should do something', function() {",
            "  assert.equal(1, 1);",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "should do something"

    def test_multiple_tests(self) -> None:
        lines = [
            "test('first', () => {",
            "  expect(1).toBe(1);",
            "});",
            "",
            "test('second', () => {",
            "  expect(2).toBe(2);",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        assert len(funcs) == 2

    def test_double_quoted_name(self) -> None:
        lines = [
            'test("should work", () => {',
            "  expect(true).toBe(true);",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "should work"

    def test_empty_file(self) -> None:
        funcs = extract_js_test_functions([])
        assert len(funcs) == 0

    def test_backtick_name(self) -> None:
        lines = [
            "test(`should work with template`, () => {",
            "  expect(true).toBe(true);",
            "});",
        ]
        funcs = extract_js_test_functions(lines)
        assert len(funcs) == 1
        assert funcs[0][0] == "should work with template"


class TestCountAssertions:
    """Tests para count_assertions."""

    def test_python_assert_statement(self) -> None:
        lines = [
            "def test_something():",
            "    result = compute()",
            "    assert result == 42",
        ]
        assert count_assertions(lines, 1, 3, is_python=True) == 1

    def test_python_multiple_asserts(self) -> None:
        lines = [
            "def test_something():",
            "    assert a == 1",
            "    assert b == 2",
            "    assert c == 3",
        ]
        assert count_assertions(lines, 1, 4, is_python=True) == 3

    def test_python_unittest_methods(self) -> None:
        lines = [
            "def test_something(self):",
            "    self.assertEqual(a, 1)",
            "    self.assertTrue(b)",
        ]
        assert count_assertions(lines, 1, 3, is_python=True) == 2

    def test_python_pytest_raises(self) -> None:
        lines = [
            "def test_raises():",
            "    with pytest.raises(ValueError):",
            "        divide(1, 0)",
        ]
        assert count_assertions(lines, 1, 3, is_python=True) == 1

    def test_python_no_assertions(self) -> None:
        lines = [
            "def test_empty():",
            "    result = compute()",
            "    print(result)",
        ]
        assert count_assertions(lines, 1, 3, is_python=True) == 0

    def test_js_expect(self) -> None:
        lines = [
            "test('something', () => {",
            "  const result = compute();",
            "  expect(result).toBe(42);",
            "});",
        ]
        assert count_assertions(lines, 1, 4, is_python=False) == 1

    def test_js_multiple_expects(self) -> None:
        lines = [
            "test('something', () => {",
            "  expect(a).toBe(1);",
            "  expect(b).toEqual({x: 1});",
            "});",
        ]
        assert count_assertions(lines, 1, 4, is_python=False) == 2

    def test_comments_not_counted(self) -> None:
        lines = [
            "def test_something():",
            "    # assert this is a comment",
            "    result = compute()",
        ]
        assert count_assertions(lines, 1, 3, is_python=True) == 0

    def test_js_comments_not_counted(self) -> None:
        lines = [
            "test('x', () => {",
            "  // expect(x).toBe(1);",
            "  console.log('test');",
            "});",
        ]
        assert count_assertions(lines, 1, 4, is_python=False) == 0

    def test_empty_range(self) -> None:
        lines = ["def test_x():", "    pass"]
        # Range start == end means empty body (but pass is body)
        assert count_assertions(lines, 1, 1, is_python=True) == 0


class TestFindTrivialAssertions:
    """Tests para find_trivial_assertions."""

    def test_assert_true(self) -> None:
        lines = [
            "def test_x():",
            "    assert True",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == 2  # line 2

    def test_assert_is_not_none(self) -> None:
        lines = [
            "def test_x():",
            "    assert result is not None",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 1

    def test_assert_is_none(self) -> None:
        lines = [
            "def test_x():",
            "    assert result is None",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 1

    def test_bare_assert_variable(self) -> None:
        lines = [
            "def test_x():",
            "    assert result",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 1

    def test_real_assertion_not_trivial(self) -> None:
        lines = [
            "def test_x():",
            "    assert result == 42",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 0

    def test_js_toBeTruthy(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(result).toBeTruthy();",
            "});",
        ]
        results = find_trivial_assertions(lines, 1, 3, is_python=False)
        assert len(results) == 1

    def test_js_toBeDefined(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(result).toBeDefined();",
            "});",
        ]
        results = find_trivial_assertions(lines, 1, 3, is_python=False)
        assert len(results) == 1

    def test_js_not_toBeNull(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(result).not.toBeNull();",
            "});",
        ]
        results = find_trivial_assertions(lines, 1, 3, is_python=False)
        assert len(results) == 1

    def test_js_real_assertion_not_trivial(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(result).toBe(42);",
            "});",
        ]
        results = find_trivial_assertions(lines, 1, 3, is_python=False)
        assert len(results) == 0

    def test_assertTrue_True(self) -> None:
        lines = [
            "def test_x(self):",
            "    self.assertTrue(True)",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 1

    def test_assertIsNotNone(self) -> None:
        lines = [
            "def test_x(self):",
            "    self.assertIsNotNone(result)",
        ]
        results = find_trivial_assertions(lines, 1, 2, is_python=True)
        assert len(results) == 1


class TestFindCatchAllExceptions:
    """Tests para find_catch_all_exceptions."""

    def test_python_except_exception_pass(self) -> None:
        lines = [
            "def test_x():",
            "    try:",
            "        result = compute()",
            "    except Exception:",
            "        pass",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 1
        assert results[0][0] == 4

    def test_python_bare_except_pass(self) -> None:
        lines = [
            "def test_x():",
            "    try:",
            "        result = compute()",
            "    except:",
            "        pass",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 1

    def test_python_except_with_raise_not_catch_all(self) -> None:
        lines = [
            "def test_x():",
            "    try:",
            "        result = compute()",
            "    except Exception as e:",
            "        raise AssertionError(str(e))",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 0

    def test_python_specific_exception_not_catch_all(self) -> None:
        """except ValueError no es catch-all."""
        lines = [
            "def test_x():",
            "    try:",
            "        result = compute()",
            "    except ValueError:",
            "        pass",
        ]
        results = find_catch_all_exceptions(lines, 1, 5, is_python=True)
        assert len(results) == 0

    def test_js_catch_all(self) -> None:
        lines = [
            "test('x', () => {",
            "  try {",
            "    compute();",
            "  } catch(e) {",
            "    // swallowed",
            "  }",
            "});",
        ]
        results = find_catch_all_exceptions(lines, 1, 7, is_python=False)
        assert len(results) == 1

    def test_empty_range(self) -> None:
        results = find_catch_all_exceptions([], 0, 0, is_python=True)
        assert len(results) == 0


class TestFindSkipsWithoutReason:
    """Tests para find_skips_without_reason."""

    def test_pytest_skip_no_args(self) -> None:
        lines = [
            "@pytest.mark.skip",
            "def test_broken():",
            "    pass",
        ]
        results = find_skips_without_reason(lines, is_python=True)
        assert len(results) == 1
        assert results[0][0] == 1

    def test_pytest_skip_empty_parens(self) -> None:
        lines = [
            "@pytest.mark.skip()",
            "def test_broken():",
            "    pass",
        ]
        results = find_skips_without_reason(lines, is_python=True)
        assert len(results) == 1

    def test_pytest_skip_with_reason_not_reported(self) -> None:
        lines = [
            "@pytest.mark.skip(reason='WIP')",
            "def test_broken():",
            "    pass",
        ]
        results = find_skips_without_reason(lines, is_python=True)
        assert len(results) == 0

    def test_unittest_skip_no_args(self) -> None:
        lines = [
            "@unittest.skip",
            "def test_broken(self):",
            "    pass",
        ]
        results = find_skips_without_reason(lines, is_python=True)
        assert len(results) == 1

    def test_unittest_skip_empty_parens(self) -> None:
        lines = [
            "@unittest.skip()",
            "def test_broken(self):",
            "    pass",
        ]
        results = find_skips_without_reason(lines, is_python=True)
        assert len(results) == 1

    def test_js_test_skip(self) -> None:
        lines = [
            "test.skip('broken', () => {",
            "  expect(1).toBe(1);",
            "});",
        ]
        results = find_skips_without_reason(lines, is_python=False)
        assert len(results) == 1

    def test_js_xit(self) -> None:
        lines = [
            "xit('broken', () => {",
            "  expect(1).toBe(1);",
            "});",
        ]
        results = find_skips_without_reason(lines, is_python=False)
        assert len(results) == 1

    def test_js_xtest(self) -> None:
        lines = [
            "xtest('broken', () => {",
            "  expect(1).toBe(1);",
            "});",
        ]
        results = find_skips_without_reason(lines, is_python=False)
        assert len(results) == 1

    def test_no_skips(self) -> None:
        lines = [
            "def test_normal():",
            "    assert True",
        ]
        results = find_skips_without_reason(lines, is_python=True)
        assert len(results) == 0


class TestIsApiTest:
    """Tests para is_api_test."""

    def test_python_client_get(self) -> None:
        lines = [
            "def test_x():",
            "    response = client.get('/api/users')",
        ]
        assert is_api_test(lines, 1, 2, is_python=True)

    def test_python_client_post(self) -> None:
        lines = [
            "def test_x():",
            "    response = client.post('/api/users', json=data)",
        ]
        assert is_api_test(lines, 1, 2, is_python=True)

    def test_python_no_api_call(self) -> None:
        lines = [
            "def test_x():",
            "    result = compute(42)",
        ]
        assert not is_api_test(lines, 1, 2, is_python=True)

    def test_js_fetch(self) -> None:
        lines = [
            "test('x', () => {",
            "  const res = await fetch('/api/users');",
            "});",
        ]
        assert is_api_test(lines, 1, 3, is_python=False)

    def test_js_supertest(self) -> None:
        lines = [
            "test('x', () => {",
            "  const res = await supertest(app).get('/api');",
            "});",
        ]
        assert is_api_test(lines, 1, 3, is_python=False)


class TestHasStatusCodeAssertion:
    """Tests para has_status_code_assertion."""

    def test_python_status_code(self) -> None:
        lines = [
            "def test_x():",
            "    response = client.get('/api')",
            "    assert response.status_code == 200",
        ]
        assert has_status_code_assertion(lines, 1, 3, is_python=True)

    def test_python_no_status_code(self) -> None:
        lines = [
            "def test_x():",
            "    response = client.get('/api')",
            "    data = response.json()",
        ]
        assert not has_status_code_assertion(lines, 1, 3, is_python=True)

    def test_js_status(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(response.statusCode).toBe(200);",
            "});",
        ]
        assert has_status_code_assertion(lines, 1, 3, is_python=False)

    def test_js_status_method(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(res).toHaveProperty('status', 200);",
            "});",
        ]
        assert has_status_code_assertion(lines, 1, 3, is_python=False)
