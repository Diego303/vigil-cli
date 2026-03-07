"""Heuristicas de cobertura significativa para tests.

Funciones auxiliares que determinan si un archivo es un archivo de test
y proveen informacion contextual para el TestQualityAnalyzer.
"""

import re
from pathlib import Path


# Patrones de archivos de test
_PYTHON_TEST_FILE = re.compile(
    r"(?:^|/)(?:test_\w+|(?:\w+_test))\.py$"
)

_JS_TEST_FILE = re.compile(
    r"(?:^|/)(?:\w+\.(?:test|spec)\.(?:js|jsx|ts|tsx|mjs|cjs))$"
)

# Directorios tipicos de tests
_TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}


def is_test_file(file_path: str) -> bool:
    """Determina si un archivo es un archivo de test.

    Criterios:
    - Python: test_*.py o *_test.py
    - JavaScript: *.test.js, *.spec.js, *.test.ts, *.spec.ts (y variantes)
    - O esta dentro de un directorio de tests conocido
    """
    normalized = file_path.replace("\\", "/")

    if _PYTHON_TEST_FILE.search(normalized):
        return True
    if _JS_TEST_FILE.search(normalized):
        return True

    # Verificar si esta en un directorio de tests
    parts = Path(normalized).parts
    return any(part in _TEST_DIRS for part in parts)


def is_python_test_file(file_path: str) -> bool:
    """Determina si es un archivo de test Python."""
    if not file_path.endswith(".py"):
        return False
    return is_test_file(file_path)


def is_js_test_file(file_path: str) -> bool:
    """Determina si es un archivo de test JavaScript/TypeScript."""
    if not file_path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        return False
    return is_test_file(file_path)


def detect_test_framework(content: str, is_python: bool) -> str | None:
    """Detecta el framework de testing usado en el archivo.

    Returns:
        "pytest", "unittest", "jest", "mocha", o None.
    """
    if is_python:
        if "import pytest" in content or "from pytest" in content:
            return "pytest"
        if "import unittest" in content or "from unittest" in content:
            return "unittest"
        # Convenciones pytest (def test_ sin import explicito)
        if re.search(r"^def test_\w+", content, re.MULTILINE):
            return "pytest"
        return None
    else:
        if re.search(r"\bdescribe\s*\(", content) and re.search(r"\bit\s*\(", content):
            return "mocha"
        if re.search(r"\btest\s*\(", content) or re.search(r"\bexpect\s*\(", content):
            return "jest"
        return None
