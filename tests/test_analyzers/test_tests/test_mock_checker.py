"""Tests para mock_checker — deteccion de mock mirrors."""

from vigil.analyzers.tests.mock_checker import (
    find_assert_values,
    find_mock_mirrors,
    find_mock_return_values,
)


class TestFindMockReturnValues:
    """Tests para find_mock_return_values."""

    def test_python_return_value_number(self) -> None:
        lines = [
            "def test_x():",
            "    mock_calc.return_value = 42",
        ]
        results = find_mock_return_values(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == "42"

    def test_python_return_value_string(self) -> None:
        lines = [
            "def test_x():",
            '    mock_service.return_value = "hello"',
        ]
        results = find_mock_return_values(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == "hello"

    def test_python_return_value_boolean(self) -> None:
        lines = [
            "def test_x():",
            "    mock_check.return_value = True",
        ]
        results = find_mock_return_values(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == "true"

    def test_python_return_value_non_literal_ignored(self) -> None:
        """Non-literal values should not be detected."""
        lines = [
            "def test_x():",
            "    mock_calc.return_value = some_variable",
        ]
        results = find_mock_return_values(lines, 1, 2, is_python=True)
        assert len(results) == 0

    def test_js_mockReturnValue(self) -> None:
        lines = [
            "test('x', () => {",
            "  const mock = jest.fn().mockReturnValue(42);",
            "});",
        ]
        results = find_mock_return_values(lines, 1, 3, is_python=False)
        assert len(results) == 1
        assert results[0][0] == "42"

    def test_js_mockResolvedValue(self) -> None:
        lines = [
            "test('x', () => {",
            '  const mock = jest.fn().mockResolvedValue("data");',
            "});",
        ]
        results = find_mock_return_values(lines, 1, 3, is_python=False)
        assert len(results) == 1
        assert results[0][0] == "data"


class TestFindAssertValues:
    """Tests para find_assert_values."""

    def test_python_assert_equals(self) -> None:
        lines = [
            "def test_x():",
            "    assert result == 42",
        ]
        results = find_assert_values(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == "42"

    def test_python_assertEqual(self) -> None:
        lines = [
            "def test_x(self):",
            "    self.assertEqual(result, 42)",
        ]
        results = find_assert_values(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == "42"

    def test_python_assert_string(self) -> None:
        lines = [
            "def test_x():",
            '    assert result == "hello"',
        ]
        results = find_assert_values(lines, 1, 2, is_python=True)
        assert len(results) == 1
        assert results[0][0] == "hello"

    def test_js_expect_toBe(self) -> None:
        lines = [
            "test('x', () => {",
            "  expect(result).toBe(42);",
            "});",
        ]
        results = find_assert_values(lines, 1, 3, is_python=False)
        assert len(results) == 1
        assert results[0][0] == "42"

    def test_js_expect_toEqual(self) -> None:
        lines = [
            "test('x', () => {",
            '  expect(result).toEqual("hello");',
            "});",
        ]
        results = find_assert_values(lines, 1, 3, is_python=False)
        assert len(results) == 1
        assert results[0][0] == "hello"


class TestFindMockMirrors:
    """Tests para find_mock_mirrors — deteccion de mock mirrors."""

    def test_python_mock_mirror_number(self) -> None:
        lines = [
            "def test_price():",
            "    mock_calc.return_value = 42",
            "    result = get_price()",
            "    assert result == 42",
        ]
        results = find_mock_mirrors(lines, 1, 4, is_python=True)
        assert len(results) == 1
        mock_line, assert_line, value = results[0]
        assert value == "42"

    def test_python_mock_mirror_string(self) -> None:
        lines = [
            "def test_name():",
            '    mock_service.return_value = "alice"',
            "    result = get_name()",
            '    assert result == "alice"',
        ]
        results = find_mock_mirrors(lines, 1, 4, is_python=True)
        assert len(results) == 1
        assert results[0][2] == "alice"

    def test_python_no_mirror(self) -> None:
        """Different values in mock and assert — not a mirror."""
        lines = [
            "def test_transform():",
            "    mock_data.return_value = 10",
            "    result = transform()",
            "    assert result == 20",
        ]
        results = find_mock_mirrors(lines, 1, 4, is_python=True)
        assert len(results) == 0

    def test_python_no_mock(self) -> None:
        """Test without mock — no mirror."""
        lines = [
            "def test_add():",
            "    result = add(2, 3)",
            "    assert result == 5",
        ]
        results = find_mock_mirrors(lines, 1, 3, is_python=True)
        assert len(results) == 0

    def test_js_mock_mirror(self) -> None:
        lines = [
            "test('price', () => {",
            "  const mock = jest.fn().mockReturnValue(42);",
            "  const result = mock();",
            "  expect(result).toBe(42);",
            "});",
        ]
        results = find_mock_mirrors(lines, 1, 5, is_python=False)
        assert len(results) == 1

    def test_js_no_mirror(self) -> None:
        lines = [
            "test('transform', () => {",
            "  const mock = jest.fn().mockReturnValue(10);",
            "  const result = transform();",
            "  expect(result).toBe(20);",
            "});",
        ]
        results = find_mock_mirrors(lines, 1, 5, is_python=False)
        assert len(results) == 0

    def test_python_mock_non_literal_not_matched(self) -> None:
        """Mock with non-literal value should not match."""
        lines = [
            "def test_x():",
            "    mock.return_value = compute_expected()",
            "    result = get_value()",
            "    assert result == 42",
        ]
        results = find_mock_mirrors(lines, 1, 4, is_python=True)
        assert len(results) == 0
