"""TestQualityAnalyzer — detecta test theater en codigo generado por IA.

Implementa reglas TEST-001 a TEST-006:
  TEST-001: Test sin assertions (funcion vacia o sin assert/expect)
  TEST-002: Assertion trivial (assert True, assert x is not None, toBeTruthy)
  TEST-003: Test que captura todas las excepciones sin verificar tipo
  TEST-004: Test marcado como skip sin justificacion
  TEST-005: Test de API sin verificacion de status code
  TEST-006: Mock que replica la implementacion (mock mirror)

Estrategia: Pattern matching con regex sobre archivos de test.
Soporta pytest (Python) y jest/mocha (JavaScript/TypeScript).
"""

import re

import structlog

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
from vigil.analyzers.tests.coverage_heuristics import (
    is_js_test_file,
    is_python_test_file,
)
from vigil.analyzers.tests.mock_checker import find_mock_mirrors
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity

logger = structlog.get_logger()


class TestQualityAnalyzer:
    """Analiza archivos de test para detectar test theater."""

    __test__ = False  # Prevent pytest collection

    @property
    def name(self) -> str:
        return "test-quality"

    @property
    def category(self) -> Category:
        return Category.TEST_QUALITY

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        """Ejecuta el analisis de calidad de tests."""
        findings: list[Finding] = []
        tests_config = config.tests

        for file_path in files:
            is_python = is_python_test_file(file_path)
            is_js = is_js_test_file(file_path)

            if not is_python and not is_js:
                continue

            try:
                content = _read_file_safe(file_path)
                if content is None:
                    continue

                lines = content.splitlines()

                # TEST-004: Skips sin justificacion (global, no por test)
                findings.extend(
                    self._check_skips(lines, file_path, is_python)
                )

                # Extraer funciones de test
                if is_python:
                    test_funcs = extract_python_test_functions(lines)
                else:
                    test_funcs = extract_js_test_functions(lines)

                if not test_funcs:
                    continue

                logger.debug(
                    "test_functions_found",
                    file=file_path,
                    count=len(test_funcs),
                )

                for test_name, start_line, end_line in test_funcs:
                    # start_line: 1-based line number of def/test (coincides
                    # with 0-based index of first body line).
                    # end_line: 0-based exclusive end of the function body.
                    body_start = start_line
                    body_end = end_line

                    # Saltar tests que estan marcados como skip
                    if _is_skipped_test(lines, start_line, is_python):
                        continue

                    # TEST-001: Test sin assertions
                    assertion_count = count_assertions(
                        lines, body_start, body_end, is_python
                    )
                    if assertion_count < tests_config.min_assertions_per_test:
                        findings.append(Finding(
                            rule_id="TEST-001",
                            category=Category.TEST_QUALITY,
                            severity=Severity.HIGH,
                            message=(
                                f"Test '{test_name}' has no assertions."
                                if assertion_count == 0
                                else (
                                    f"Test '{test_name}' has only "
                                    f"{assertion_count} assertion(s) "
                                    f"(minimum: {tests_config.min_assertions_per_test})."
                                )
                            ),
                            location=Location(
                                file=file_path,
                                line=start_line,
                                snippet=lines[start_line - 1].strip() if start_line <= len(lines) else None,
                            ),
                            suggestion=(
                                "Add at least one assert to verify the expected behavior. "
                                "A test without assertions only verifies that code doesn't crash."
                            ),
                            metadata={
                                "test_name": test_name,
                                "assertion_count": assertion_count,
                                "min_required": tests_config.min_assertions_per_test,
                            },
                        ))

                    # TEST-002: Assertions triviales
                    if tests_config.detect_trivial_asserts:
                        trivials = find_trivial_assertions(
                            lines, body_start, body_end, is_python,
                        )
                        # Solo reportar si TODAS las assertions son triviales
                        if trivials and assertion_count > 0 and len(trivials) >= assertion_count:
                            for line_num, snippet in trivials:
                                findings.append(Finding(
                                    rule_id="TEST-002",
                                    category=Category.TEST_QUALITY,
                                    severity=Severity.MEDIUM,
                                    message=(
                                        f"Trivial assertion in test '{test_name}'. "
                                        f"Assertion only checks a basic condition without "
                                        f"verifying specific behavior."
                                    ),
                                    location=Location(
                                        file=file_path,
                                        line=line_num,
                                        snippet=snippet,
                                    ),
                                    suggestion=(
                                        "Replace with a meaningful assertion that verifies "
                                        "specific expected values or behavior."
                                    ),
                                    metadata={
                                        "test_name": test_name,
                                    },
                                ))

                    # TEST-003: Catch-all exceptions
                    catch_alls = find_catch_all_exceptions(
                        lines, body_start, body_end, is_python,
                    )
                    for line_num, snippet in catch_alls:
                        findings.append(Finding(
                            rule_id="TEST-003",
                            category=Category.TEST_QUALITY,
                            severity=Severity.MEDIUM,
                            message=(
                                f"Test '{test_name}' catches all exceptions "
                                f"without verifying the type."
                            ),
                            location=Location(
                                file=file_path,
                                line=line_num,
                                snippet=snippet,
                            ),
                            suggestion=(
                                "Use pytest.raises(SpecificException) to verify "
                                "the expected exception type, or remove the "
                                "try/except block."
                            ),
                            metadata={
                                "test_name": test_name,
                            },
                        ))

                    # TEST-005: API test sin status code assertion
                    if is_api_test(lines, body_start, body_end, is_python):
                        if not has_status_code_assertion(
                            lines, body_start, body_end, is_python
                        ):
                            findings.append(Finding(
                                rule_id="TEST-005",
                                category=Category.TEST_QUALITY,
                                severity=Severity.MEDIUM,
                                message=(
                                    f"API test '{test_name}' does not verify "
                                    f"the response status code."
                                ),
                                location=Location(
                                    file=file_path,
                                    line=start_line,
                                    snippet=lines[start_line - 1].strip() if start_line <= len(lines) else None,
                                ),
                                suggestion=(
                                    "Add an assertion on the response status code: "
                                    "assert response.status_code == 200 (Python) or "
                                    "expect(response.status).toBe(200) (JavaScript)."
                                ),
                                metadata={
                                    "test_name": test_name,
                                },
                            ))

                    # TEST-006: Mock mirrors
                    if tests_config.detect_mock_mirrors:
                        mirrors = find_mock_mirrors(
                            lines, body_start, body_end, is_python,
                        )
                        for mock_line, assert_line, value in mirrors:
                            findings.append(Finding(
                                rule_id="TEST-006",
                                category=Category.TEST_QUALITY,
                                severity=Severity.MEDIUM,
                                message=(
                                    f"Test '{test_name}' asserts a value ({value!r}) "
                                    f"that is the same as the mock return value. "
                                    f"This test only verifies the mock works, "
                                    f"not the actual implementation."
                                ),
                                location=Location(
                                    file=file_path,
                                    line=assert_line,
                                    snippet=lines[assert_line - 1].strip() if assert_line <= len(lines) else None,
                                ),
                                suggestion=(
                                    "Use a mock to isolate dependencies, but assert "
                                    "on values derived from test inputs, not on the "
                                    "mock's return value itself."
                                ),
                                metadata={
                                    "test_name": test_name,
                                    "mock_line": mock_line,
                                    "assert_line": assert_line,
                                    "value": value,
                                },
                            ))

            except Exception as e:
                logger.warning("test_quality_file_error", file=file_path, error=str(e))

        return findings

    def _check_skips(
        self,
        lines: list[str],
        file_path: str,
        is_python: bool,
    ) -> list[Finding]:
        """TEST-004: Detecta tests marcados como skip sin justificacion."""
        findings: list[Finding] = []
        skips = find_skips_without_reason(lines, is_python)

        for line_num, snippet in skips:
            findings.append(Finding(
                rule_id="TEST-004",
                category=Category.TEST_QUALITY,
                severity=Severity.LOW,
                message=(
                    "Test marked as skip without a reason. "
                    "Skipped tests without justification hide potential issues."
                ),
                location=Location(
                    file=file_path,
                    line=line_num,
                    snippet=snippet,
                ),
                suggestion=(
                    "Add a reason: @pytest.mark.skip(reason='...') (Python) "
                    "or add a comment explaining why the test is skipped."
                ),
            ))

        return findings


def _is_skipped_test(lines: list[str], start_line: int, is_python: bool) -> bool:
    """Verifica si un test esta marcado como skip.

    Para Python: busca @pytest.mark.skip o @unittest.skip en las lineas
    anteriores al def.
    Para JavaScript: busca test.skip / it.skip / xit / xtest en la linea del test.
    """
    if is_python:
        # Mirar hasta 3 lineas antes del def para buscar decoradores skip
        def_idx = start_line - 1  # 0-based
        check_start = max(0, def_idx - 3)
        for idx in range(check_start, def_idx):
            stripped = lines[idx].strip()
            if "@pytest.mark.skip" in stripped or "@unittest.skip" in stripped:
                return True
        return False
    else:
        # Para JS, test.skip/it.skip/xit/xtest estan en la misma linea que la declaracion
        test_line = lines[start_line - 1] if start_line <= len(lines) else ""
        stripped = test_line.strip()
        return bool(re.match(r"\s*(?:(?:test|it)\.skip|xit|xtest)\s*\(", stripped))


def _read_file_safe(file_path: str) -> str | None:
    """Lee un archivo de forma segura, retornando None si no se puede leer."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IOError):
        return None
