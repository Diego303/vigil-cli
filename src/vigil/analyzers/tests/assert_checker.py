"""Verificacion de assertions en tests — detecta tests vacios y triviales.

Soporta pytest (Python) y jest/mocha (JavaScript/TypeScript).
"""

import re


# ──────────────────────────────────────────────
# Deteccion de funciones / bloques de test
# ──────────────────────────────────────────────

# Python: def test_something(...): or async def test_something(...):
_PYTHON_TEST_FUNC = re.compile(
    r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>test_\w+)\s*\(",
)

# JavaScript: test("...", ...) / it("...", ...)
_JS_TEST_FUNC = re.compile(
    r"""^(?P<indent>\s*)(?:test|it)\s*\(\s*(?P<quote>['"`])(?P<name>.*?)(?P=quote)""",
)

# ──────────────────────────────────────────────
# Assertion patterns
# ──────────────────────────────────────────────

# Python assertions
_PYTHON_ASSERT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bassert\b"),
    re.compile(r"\.assert\w+\s*\("),         # unittest: assertEqual, assertTrue, etc.
    re.compile(r"pytest\.raises\s*\("),
    re.compile(r"pytest\.warns\s*\("),
    re.compile(r"pytest\.approx\s*\("),
    re.compile(r"\.should\b"),                # should-style
]

# JavaScript assertions
_JS_ASSERT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bexpect\s*\("),
    re.compile(r"\bassert\s*[\.(]"),
    re.compile(r"\.should\b"),
    re.compile(r"\.to\b"),
    re.compile(r"\.toEqual\b"),
    re.compile(r"\.toBe\b"),
    re.compile(r"\.toThrow\b"),
    re.compile(r"\.rejects\b"),
    re.compile(r"\.resolves\b"),
]

# ──────────────────────────────────────────────
# Trivial assertion patterns (TEST-002)
# ──────────────────────────────────────────────

_PYTHON_TRIVIAL_ASSERTS: list[re.Pattern[str]] = [
    # assert True / assert False  (assert False is trivially failing, still trivial)
    re.compile(r"^\s*assert\s+True\s*$"),
    re.compile(r"^\s*assert\s+True\s*,"),
    # assert x is not None (solo)
    re.compile(r"^\s*assert\s+\w+\s+is\s+not\s+None\s*$"),
    re.compile(r"^\s*assert\s+\w+\s+is\s+not\s+None\s*,"),
    # assert x is None  (solo)
    re.compile(r"^\s*assert\s+\w+\s+is\s+None\s*$"),
    re.compile(r"^\s*assert\s+\w+\s+is\s+None\s*,"),
    # assertTrue(True)
    re.compile(r"\.assertTrue\s*\(\s*True\s*\)"),
    # assertIsNotNone(x) sin mas checks
    re.compile(r"\.assertIsNotNone\s*\(\s*\w+\s*\)"),
    # assertIsNone(x) sin mas checks
    re.compile(r"\.assertIsNone\s*\(\s*\w+\s*\)"),
    # assert x  (bare assertion on variable — no comparison)
    re.compile(r"^\s*assert\s+\w+\s*$"),
    re.compile(r"^\s*assert\s+\w+\s*,"),
]

_JS_TRIVIAL_ASSERTS: list[re.Pattern[str]] = [
    # expect(x).toBeTruthy()
    re.compile(r"expect\s*\([^)]+\)\s*\.toBeTruthy\s*\(\s*\)"),
    # expect(x).toBeDefined()
    re.compile(r"expect\s*\([^)]+\)\s*\.toBeDefined\s*\(\s*\)"),
    # expect(x).not.toBeNull()
    re.compile(r"expect\s*\([^)]+\)\s*\.not\s*\.toBeNull\s*\(\s*\)"),
    # expect(x).not.toBeUndefined()
    re.compile(r"expect\s*\([^)]+\)\s*\.not\s*\.toBeUndefined\s*\(\s*\)"),
    # expect(x).toBe(true)
    re.compile(r"expect\s*\([^)]+\)\s*\.toBe\s*\(\s*true\s*\)"),
]

# ──────────────────────────────────────────────
# Catch-all exception patterns (TEST-003)
# ──────────────────────────────────────────────

# Python: except Exception: / except BaseException: / except: (bare)
_PYTHON_CATCH_ALL = re.compile(
    r"^\s*except\s*(?:(?:Base)?Exception)?\s*(?::|as\s+\w+\s*:)"
)

# JavaScript: catch(e) { ... } / catch(error) { ... }  (no filtering)
_JS_CATCH_ALL = re.compile(
    r"^\s*\}\s*catch\s*\(\s*\w+\s*\)\s*\{"
)

# ──────────────────────────────────────────────
# Skip patterns (TEST-004)
# ──────────────────────────────────────────────

# Python: @pytest.mark.skip without reason
_PYTHON_SKIP_NO_REASON = re.compile(
    r"@pytest\.mark\.skip\s*$"
)
# Python: @pytest.mark.skip() without reason keyword
_PYTHON_SKIP_NO_REASON_PARENS = re.compile(
    r"@pytest\.mark\.skip\s*\(\s*\)"
)
# Python: @unittest.skip without reason
_UNITTEST_SKIP_NO_REASON = re.compile(
    r"@unittest\.skip\s*$"
)
_UNITTEST_SKIP_NO_REASON_PARENS = re.compile(
    r"@unittest\.skip\s*\(\s*\)"
)

# JavaScript: test.skip(...) / it.skip(...) / xit(...) / xtest(...)
_JS_SKIP_PATTERN = re.compile(
    r"^\s*(?:(?:test|it)\.skip|xit|xtest)\s*\("
)

# ──────────────────────────────────────────────
# API test detection (TEST-005)
# ──────────────────────────────────────────────

# Python: client.get/post/put/delete/patch calls
_PYTHON_API_CALL = re.compile(
    r"(?:client|response|res|resp)\s*[\.\=].*\b(?:get|post|put|delete|patch)\s*\(",
    re.IGNORECASE,
)

# JavaScript: request(app).get/post/etc. or fetch() or axios.get() etc.
_JS_API_CALL = re.compile(
    r"(?:request\s*\([^)]*\)|supertest\s*\([^)]*\)|fetch\s*\(|axios\s*\.(?:get|post|put|delete|patch)\s*\()",
    re.IGNORECASE,
)

# Status code assertion patterns
_PYTHON_STATUS_ASSERT = re.compile(
    r"(?:status_code|status|\.status\b|\.code\b)",
    re.IGNORECASE,
)

_JS_STATUS_ASSERT = re.compile(
    r"(?:\.status\s*\(|\.statusCode|\.status\b|toHaveProperty\s*\(\s*['\"]status|expect\s*\([^)]*\)\.toBe\s*\(\s*[245]\d\d)",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────
# Test body extraction
# ──────────────────────────────────────────────

def extract_python_test_functions(
    lines: list[str],
) -> list[tuple[str, int, int]]:
    """Extrae funciones de test Python con nombre, linea inicio, linea fin.

    Returns:
        Lista de (nombre, linea_inicio_1based, linea_fin_0based_exclusive).
        linea_inicio es la linea 'def test_...' (1-based).
        linea_fin es el indice 0-based de la primera linea fuera del cuerpo (exclusive).
        Nota: start coincide con el indice 0-based de la primera linea del cuerpo,
        lo que permite usar (start, end) directamente como range para iterar el body.
    """
    functions: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lines):
        match = _PYTHON_TEST_FUNC.match(lines[i])
        if match:
            name = match.group("name")
            indent_len = len(match.group("indent"))
            start = i + 1  # 1-based line number (also == 0-based body start)
            # Verificar si es single-line: def test_x(): assert True
            def_line = lines[i]
            colon_idx = def_line.find("):")
            has_inline_body = (
                colon_idx >= 0
                and def_line[colon_idx + 2:].strip() != ""
            )
            # Buscar fin del cuerpo: siguiente linea con misma o menor indentacion
            # o fin de archivo
            end = i + 1
            while end < len(lines):
                line = lines[end]
                # Lineas vacias no terminan la funcion
                if not line.strip():
                    end += 1
                    continue
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_len:
                    break
                end += 1
            # end apunta a la primera linea fuera de la funcion (0-based exclusive)
            # Para single-line functions, incluir la linea del def como parte del body
            if has_inline_body:
                # El cuerpo esta en la misma linea que el def, asi que
                # retrocedemos start para que range(start, end) incluya la linea del def
                functions.append((name, i, end))
            else:
                functions.append((name, start, end))
            i = end
        else:
            i += 1
    return functions


def extract_js_test_functions(
    lines: list[str],
) -> list[tuple[str, int, int]]:
    """Extrae bloques de test JavaScript (test/it) con nombre, linea inicio, linea fin.

    Usa heuristica de conteo de llaves para determinar el final del bloque.
    """
    functions: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lines):
        match = _JS_TEST_FUNC.match(lines[i])
        if match:
            name = match.group("name")
            start = i + 1  # 1-based

            # Contar llaves para encontrar el fin del bloque
            brace_count = 0
            found_open = False
            end = i
            while end < len(lines):
                for ch in lines[end]:
                    if ch == "{":
                        brace_count += 1
                        found_open = True
                    elif ch == "}":
                        brace_count -= 1
                if found_open and brace_count <= 0:
                    end += 1
                    break
                end += 1

            functions.append((name, start, end))
            i = end
        else:
            i += 1
    return functions


def count_assertions(lines: list[str], start: int, end: int, is_python: bool) -> int:
    """Cuenta assertions dentro de un rango de lineas (indices 0-based).

    Args:
        lines: Todas las lineas del archivo.
        start: Indice 0-based de inicio (inclusive, primera linea del cuerpo).
        end: Indice 0-based de fin (exclusive).
        is_python: True si es Python, False si es JavaScript.

    Returns:
        Numero de assertions encontradas.
    """
    patterns = _PYTHON_ASSERT_PATTERNS if is_python else _JS_ASSERT_PATTERNS
    count = 0
    # Para Python, el cuerpo empieza despues del def, para JS despues del test(
    body_start = start  # Ya es la primera linea del cuerpo (0-based)
    for idx in range(body_start, min(end, len(lines))):
        line = lines[idx].strip()
        if not line:
            continue
        if is_python and line.startswith("#"):
            continue
        if not is_python and line.startswith("//"):
            continue
        for pattern in patterns:
            if pattern.search(line):
                count += 1
                break
    return count


def find_trivial_assertions(
    lines: list[str], start: int, end: int, is_python: bool,
) -> list[tuple[int, str]]:
    """Encuentra assertions triviales en un rango de lineas.

    Returns:
        Lista de (linea_1based, snippet) de assertions triviales.
    """
    patterns = _PYTHON_TRIVIAL_ASSERTS if is_python else _JS_TRIVIAL_ASSERTS
    results: list[tuple[int, str]] = []
    for idx in range(start, min(end, len(lines))):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in patterns:
            if pattern.search(stripped):
                results.append((idx + 1, stripped))
                break
    return results


def find_catch_all_exceptions(
    lines: list[str], start: int, end: int, is_python: bool,
) -> list[tuple[int, str]]:
    """Encuentra bloques catch-all de excepciones en tests.

    Returns:
        Lista de (linea_1based, snippet).
    """
    pattern = _PYTHON_CATCH_ALL if is_python else _JS_CATCH_ALL
    results: list[tuple[int, str]] = []
    for idx in range(start, min(end, len(lines))):
        stripped = lines[idx].strip()
        if pattern.match(stripped):
            # Verificar que el bloque catch no tiene un re-raise o tipo especifico
            if is_python:
                # except Exception as e: / except: — es catch-all
                # Pero si la siguiente linea es raise, no es catch-all silencioso
                next_idx = idx + 1
                while next_idx < min(end, len(lines)):
                    next_line = lines[next_idx].strip()
                    if next_line:
                        if next_line.startswith("raise") or next_line.startswith("pytest.raises"):
                            break
                        if next_line == "pass":
                            results.append((idx + 1, stripped))
                        break
                    next_idx += 1
                else:
                    # Llegamos al final sin encontrar nada — bloque vacio
                    results.append((idx + 1, stripped))
            else:
                results.append((idx + 1, stripped))
    return results


def find_skips_without_reason(
    lines: list[str], is_python: bool,
) -> list[tuple[int, str]]:
    """Encuentra tests marcados como skip sin justificacion.

    Returns:
        Lista de (linea_1based, snippet).
    """
    results: list[tuple[int, str]] = []
    if is_python:
        skip_patterns = [
            _PYTHON_SKIP_NO_REASON,
            _PYTHON_SKIP_NO_REASON_PARENS,
            _UNITTEST_SKIP_NO_REASON,
            _UNITTEST_SKIP_NO_REASON_PARENS,
        ]
        for i, line in enumerate(lines):
            stripped = line.strip()
            for pattern in skip_patterns:
                if pattern.search(stripped):
                    results.append((i + 1, stripped))
                    break
    else:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if _JS_SKIP_PATTERN.search(stripped):
                results.append((i + 1, stripped))
    return results


def is_api_test(lines: list[str], start: int, end: int, is_python: bool) -> bool:
    """Determina si un test contiene llamadas a una API HTTP."""
    pattern = _PYTHON_API_CALL if is_python else _JS_API_CALL
    for idx in range(start, min(end, len(lines))):
        if pattern.search(lines[idx]):
            return True
    return False


def has_status_code_assertion(
    lines: list[str], start: int, end: int, is_python: bool,
) -> bool:
    """Verifica si un test tiene alguna asercion sobre status code."""
    pattern = _PYTHON_STATUS_ASSERT if is_python else _JS_STATUS_ASSERT
    for idx in range(start, min(end, len(lines))):
        if pattern.search(lines[idx]):
            return True
    return False
