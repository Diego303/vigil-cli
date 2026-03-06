"""Descubre archivos a escanear segun configuracion."""

import os
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Extensiones por lenguaje soportado
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"],
}

# Archivos de dependencias (siempre se incluyen independientemente del filtro de lenguaje)
DEPENDENCY_FILES: set[str] = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "package-lock.json",
}


def collect_files(
    paths: list[str],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    languages: list[str] | None = None,
) -> list[str]:
    """Recopila archivos a escanear.

    Args:
        paths: Directorios o archivos raiz a escanear.
        include: Patrones de inclusion (subdirectorios).
        exclude: Patrones de exclusion.
        languages: Lenguajes a incluir (filtra por extension).

    Returns:
        Lista de rutas absolutas de archivos a escanear.
    """
    exclude = exclude or []
    languages = languages or list(LANGUAGE_EXTENSIONS.keys())

    allowed_extensions = set()
    for lang in languages:
        allowed_extensions.update(LANGUAGE_EXTENSIONS.get(lang, []))

    collected: list[str] = []

    for path_str in paths:
        root = Path(path_str).resolve()

        if root.is_file():
            if _should_include_file(root, allowed_extensions, exclude):
                collected.append(str(root))
            continue

        if not root.is_dir():
            logger.warning("path_not_found", path=path_str)
            continue

        # Usar os.walk con pruning para evitar recorrer directorios excluidos
        exclude_normalized = {p.rstrip("/") for p in exclude}
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune: no recorrer subdirectorios excluidos (in-place)
            dirnames[:] = [d for d in dirnames if d not in exclude_normalized]

            for fname in filenames:
                file_path = Path(dirpath) / fname
                if _should_include_file(file_path, allowed_extensions, exclude):
                    collected.append(str(file_path))

    # Deduplica preservando orden
    seen: set[str] = set()
    unique: list[str] = []
    for f in collected:
        if f not in seen:
            seen.add(f)
            unique.append(f)

    logger.debug("files_collected", count=len(unique))
    return unique


def _should_include_file(
    file_path: Path,
    allowed_extensions: set[str],
    exclude: list[str],
) -> bool:
    """Determina si un archivo debe incluirse en el scan."""
    path_str = str(file_path)

    # Excluir por patrones (match por componente de path, no substring)
    parts = file_path.parts
    for pattern in exclude:
        normalized = pattern.rstrip("/")
        if normalized in parts:
            return False

    # Siempre incluir archivos de dependencias
    if file_path.name in DEPENDENCY_FILES:
        return True

    # Filtrar por extension de lenguaje
    return file_path.suffix in allowed_extensions
