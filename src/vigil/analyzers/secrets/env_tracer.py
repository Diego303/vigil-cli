"""Traza valores de .env.example al codigo fuente.

Lee .env.example (o .env.sample) y extrae los valores de ejemplo.
Luego busca esos mismos valores en el codigo fuente. Si encuentra
API_KEY=your-api-key-here en .env.example y api_key = "your-api-key-here"
en codigo, es una señal clara de que el agente de IA copio el placeholder.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Nombres de archivos de env example a buscar
ENV_EXAMPLE_FILES: list[str] = [
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.defaults",
    "env.example",
    "env.sample",
]

# Valores que son demasiado genericos para trazar
_GENERIC_VALUES: set[str] = {
    "true", "false", "yes", "no", "on", "off",
    "0", "1", "none", "null", "undefined",
    "localhost", "127.0.0.1", "0.0.0.0",
    "development", "production", "staging", "test",
    "debug", "info", "warning", "error",
    "3000", "8000", "8080", "5000", "5432", "3306", "6379", "27017",
}


@dataclass
class EnvExampleEntry:
    """Una entrada de un archivo .env.example."""

    key: str
    value: str
    file: str
    line: int


def find_env_example_files(root: str) -> list[Path]:
    """Encuentra archivos .env.example en el directorio raiz."""
    root_path = Path(root)
    found: list[Path] = []

    if root_path.is_file():
        root_path = root_path.parent

    for name in ENV_EXAMPLE_FILES:
        candidate = root_path / name
        if candidate.is_file():
            found.append(candidate)

    return found


def parse_env_example(file_path: Path) -> list[EnvExampleEntry]:
    """Parsea un archivo .env.example y extrae key=value pairs."""
    entries: list[EnvExampleEntry] = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return entries

    for i, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Formato: KEY=value o KEY="value" o KEY='value'
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()

            # Quitar comillas si las tiene
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            # Ignorar valores vacios y genericos
            if not value or value.lower() in _GENERIC_VALUES:
                continue

            # Ignorar valores que son solo variables de referencia
            if value.startswith("${") or value.startswith("$"):
                continue

            entries.append(EnvExampleEntry(
                key=key, value=value, file=str(file_path), line=i,
            ))

    return entries


def find_env_values_in_code(
    content: str,
    entries: list[EnvExampleEntry],
) -> list[tuple[int, EnvExampleEntry]]:
    """Busca valores de .env.example en el codigo fuente.

    Args:
        content: Contenido del archivo de codigo.
        entries: Entradas del .env.example.

    Returns:
        Lista de (line_number, entry) donde se encontro el valor.
    """
    matches: list[tuple[int, EnvExampleEntry]] = []
    lines = content.splitlines()

    for entry in entries:
        value = entry.value
        # Solo buscar valores con longitud minima para evitar falsos positivos
        if len(value) < 5:
            continue

        # Escapar el valor para busqueda exacta en regex
        escaped = re.escape(value)
        pattern = re.compile(
            rf"""['"]({escaped})['"]""",
        )

        for i, line in enumerate(lines):
            # Ignorar comentarios
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            if pattern.search(line):
                matches.append((i + 1, entry))

    return matches
