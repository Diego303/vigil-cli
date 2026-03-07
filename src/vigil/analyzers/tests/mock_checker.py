"""Deteccion de mocks que replican la implementacion (mock mirrors).

TEST-006: Un mock que retorna un valor literal que se usa directamente en
el assert del test no prueba nada real — el test solo verifica que el mock
devuelve lo que se le dijo que devuelva.

Ejemplo problematico:
    mock_calculate.return_value = 42
    result = calculate()
    assert result == 42  # <-- solo prueba que el mock funciona

Heuristicas:
1. Detectar mock.return_value = <literal>
2. Buscar assert ... == <mismo_literal> en el mismo test
3. Si coinciden, es probable mock mirror.
"""

import re


# Mock return value patterns
_PYTHON_MOCK_RETURN = re.compile(
    r"""(?P<mock_name>\w+)\.return_value\s*=\s*(?P<value>.+)$"""
)

_PYTHON_MOCK_PATCH_RETURN = re.compile(
    r"""@(?:unittest\.)?mock\.patch\s*\([^)]*return_value\s*=\s*(?P<value>.+?)\s*[,)]"""
)

_JS_MOCK_RETURN = re.compile(
    r"""(?:jest\.fn|mock|stub)\s*\(\s*\)\s*\.mockReturnValue\s*\(\s*(?P<value>.+?)\s*\)"""
)

_JS_MOCK_RESOLVED = re.compile(
    r"""(?:jest\.fn|mock|stub)\s*\(\s*\)\s*\.mockResolvedValue\s*\(\s*(?P<value>.+?)\s*\)"""
)

# Literal value pattern — matches numbers, strings, booleans, None/null, simple dicts/lists
_LITERAL_PATTERN = re.compile(
    r"""^(?:"""
    r"""-?\d+(?:\.\d+)?"""            # numeros
    r"""|'[^']*'"""                   # single-quoted strings
    r"""|"[^"]*\""""                  # double-quoted strings
    r"""|True|False|None"""           # Python booleans/None
    r"""|true|false|null|undefined""" # JS booleans/null
    r"""|{\s*}|\[\s*\]"""            # empty dict/list
    r""")$"""
)


def find_mock_return_values(
    lines: list[str], start: int, end: int, is_python: bool,
) -> list[tuple[str, int]]:
    """Encuentra valores de retorno de mocks en un rango de lineas.

    Returns:
        Lista de (valor_normalizado, linea_1based).
    """
    results: list[tuple[str, int]] = []

    for idx in range(start, min(end, len(lines))):
        stripped = lines[idx].strip()

        if is_python:
            match = _PYTHON_MOCK_RETURN.search(stripped)
            if match:
                value = match.group("value").strip()
                if _is_literal(value):
                    results.append((_normalize_value(value), idx + 1))
                continue
            match = _PYTHON_MOCK_PATCH_RETURN.search(stripped)
            if match:
                value = match.group("value").strip()
                if _is_literal(value):
                    results.append((_normalize_value(value), idx + 1))
        else:
            for pattern in (_JS_MOCK_RETURN, _JS_MOCK_RESOLVED):
                match = pattern.search(stripped)
                if match:
                    value = match.group("value").strip()
                    if _is_literal(value):
                        results.append((_normalize_value(value), idx + 1))
                    break

    return results


def find_assert_values(
    lines: list[str], start: int, end: int, is_python: bool,
) -> list[tuple[str, int]]:
    """Encuentra valores literales usados en assertions.

    Returns:
        Lista de (valor_normalizado, linea_1based).
    """
    results: list[tuple[str, int]] = []

    for idx in range(start, min(end, len(lines))):
        stripped = lines[idx].strip()

        if is_python:
            # assert result == <literal>
            match = re.search(r"assert\s+\w+\s*==\s*(.+?)(?:\s*,\s*['\"].*)?$", stripped)
            if match:
                value = match.group(1).strip()
                if _is_literal(value):
                    results.append((_normalize_value(value), idx + 1))
                continue
            # assertEqual(result, <literal>)
            match = re.search(r"assertEqual\s*\(\s*\w+\s*,\s*(.+?)\s*\)", stripped)
            if match:
                value = match.group(1).strip()
                if _is_literal(value):
                    results.append((_normalize_value(value), idx + 1))
        else:
            # expect(result).toBe(<literal>) / toEqual(<literal>)
            match = re.search(
                r"expect\s*\([^)]+\)\s*\.(?:toBe|toEqual|toStrictEqual)\s*\(\s*(.+?)\s*\)",
                stripped,
            )
            if match:
                value = match.group(1).strip()
                if _is_literal(value):
                    results.append((_normalize_value(value), idx + 1))

    return results


def find_mock_mirrors(
    lines: list[str], start: int, end: int, is_python: bool,
) -> list[tuple[int, int, str]]:
    """Detecta mock mirrors: mock return value que coincide con assert value.

    Returns:
        Lista de (mock_line_1based, assert_line_1based, valor).
    """
    mock_values = find_mock_return_values(lines, start, end, is_python)
    assert_values = find_assert_values(lines, start, end, is_python)

    if not mock_values or not assert_values:
        return []

    mirrors: list[tuple[int, int, str]] = []
    mock_value_set = {v: line for v, line in mock_values}

    for assert_val, assert_line in assert_values:
        if assert_val in mock_value_set:
            mirrors.append((mock_value_set[assert_val], assert_line, assert_val))

    return mirrors


def _is_literal(value: str) -> bool:
    """Verifica si un valor es un literal simple."""
    return _LITERAL_PATTERN.match(value.strip()) is not None


def _normalize_value(value: str) -> str:
    """Normaliza un valor para comparacion.

    Quita comillas, espacios, convierte True/true, False/false, None/null.
    """
    value = value.strip()
    # Quitar comillas
    if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
        return value[1:-1]
    # Normalizar booleans/null
    lower = value.lower()
    if lower in ("true",):
        return "true"
    if lower in ("false",):
        return "false"
    if lower in ("none", "null", "undefined"):
        return "null"
    return value
