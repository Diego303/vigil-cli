"""Parsers para archivos de dependencias de diferentes ecosistemas."""

from dataclasses import dataclass
from pathlib import Path
import json
import re

import structlog

logger = structlog.get_logger()


@dataclass
class DeclaredDependency:
    """Una dependencia declarada en un archivo de configuracion."""

    name: str
    version_spec: str | None
    source_file: str
    line_number: int
    ecosystem: str  # "pypi" | "npm"
    is_dev: bool = False


def parse_requirements_txt(path: Path) -> list[DeclaredDependency]:
    """Parsea requirements.txt / requirements-dev.txt."""
    deps: list[DeclaredDependency] = []
    is_dev = "dev" in path.name

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("parse_error", file=str(path), error=str(e))
        return deps

    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip environment markers (e.g., "; sys_platform == 'win32'")
        line_no_marker = line.split(";")[0].strip()
        # Patterns: package==1.0, package>=1.0, package~=1.0, package[extras]>=1.0, package
        match = re.match(
            r"^([a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?)"
            r"(\[[a-zA-Z0-9_,.-]+\])?"
            r"\s*([>=<!~]+.*)?$",
            line_no_marker,
        )
        if match:
            name = match.group(1)
            version = match.group(4)
            if version:
                version = version.strip()
            deps.append(
                DeclaredDependency(
                    name=name,
                    version_spec=version or None,
                    source_file=str(path),
                    line_number=i,
                    ecosystem="pypi",
                    is_dev=is_dev,
                )
            )

    return deps


def parse_pyproject_toml(path: Path) -> list[DeclaredDependency]:
    """Parsea pyproject.toml [project.dependencies] y [project.optional-dependencies]."""
    deps: list[DeclaredDependency] = []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("parse_error", file=str(path), error=str(e))
        return deps

    # Usar tomllib (stdlib en 3.11+) con fallback a tomli
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            logger.warning("toml_unavailable", file=str(path))
            return deps

    try:
        data = tomllib.loads(text)
    except Exception as e:
        logger.warning("toml_parse_error", file=str(path), error=str(e))
        return deps

    # Calcular numeros de linea aproximados para cada dependencia
    lines = text.splitlines()
    line_map = _build_toml_line_map(lines)

    # [project.dependencies]
    for dep_str in data.get("project", {}).get("dependencies", []):
        name_match = re.match(r"^([a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?)", dep_str)
        if name_match:
            name = name_match.group(1)
            version_part = dep_str[len(name):].strip()
            # Quitar extras bracket si presente
            if version_part.startswith("["):
                bracket_end = version_part.find("]")
                if bracket_end != -1:
                    version_part = version_part[bracket_end + 1 :].strip()
            line_no = line_map.get(name.lower(), 0)
            deps.append(
                DeclaredDependency(
                    name=name,
                    version_spec=version_part or None,
                    source_file=str(path),
                    line_number=line_no,
                    ecosystem="pypi",
                    is_dev=False,
                )
            )

    # [project.optional-dependencies]
    for group, group_deps in (
        data.get("project", {}).get("optional-dependencies", {}).items()
    ):
        is_dev = group in ("dev", "test", "testing", "development")
        for dep_str in group_deps:
            name_match = re.match(
                r"^([a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?)", dep_str
            )
            if name_match:
                name = name_match.group(1)
                version_part = dep_str[len(name):].strip()
                if version_part.startswith("["):
                    bracket_end = version_part.find("]")
                    if bracket_end != -1:
                        version_part = version_part[bracket_end + 1 :].strip()
                line_no = line_map.get(name.lower(), 0)
                deps.append(
                    DeclaredDependency(
                        name=name,
                        version_spec=version_part or None,
                        source_file=str(path),
                        line_number=line_no,
                        ecosystem="pypi",
                        is_dev=is_dev,
                    )
                )

    return deps


def parse_package_json(path: Path) -> list[DeclaredDependency]:
    """Parsea package.json dependencies y devDependencies."""
    deps: list[DeclaredDependency] = []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("parse_error", file=str(path), error=str(e))
        return deps

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("json_parse_error", file=str(path), error=str(e))
        return deps

    # Calcular numeros de linea
    lines = text.splitlines()

    for name, version in data.get("dependencies", {}).items():
        line_no = _find_json_key_line(lines, name)
        deps.append(
            DeclaredDependency(
                name=name,
                version_spec=version if isinstance(version, str) else None,
                source_file=str(path),
                line_number=line_no,
                ecosystem="npm",
                is_dev=False,
            )
        )

    for name, version in data.get("devDependencies", {}).items():
        line_no = _find_json_key_line(lines, name)
        deps.append(
            DeclaredDependency(
                name=name,
                version_spec=version if isinstance(version, str) else None,
                source_file=str(path),
                line_number=line_no,
                ecosystem="npm",
                is_dev=True,
            )
        )

    return deps


def find_and_parse_all(root: str) -> list[DeclaredDependency]:
    """Descubre y parsea todos los archivos de dependencias en un directorio.

    Usa os.walk con pruning de directorios para evitar recorrer .venv, node_modules, etc.
    """
    import os

    root_path = Path(root).resolve()

    if not root_path.is_dir():
        logger.warning("root_not_dir", path=root)
        return []

    all_deps: list[DeclaredDependency] = []
    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", ".tox", ".mypy_cache"}

    dep_filenames = {"pyproject.toml", "package.json"}
    req_pattern = re.compile(r"^requirements.*\.txt$")

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune: eliminar subdirectorios que no queremos recorrer (in-place)
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for fname in filenames:
            fpath = Path(dirpath) / fname

            if req_pattern.match(fname):
                all_deps.extend(parse_requirements_txt(fpath))
            elif fname == "pyproject.toml":
                all_deps.extend(parse_pyproject_toml(fpath))
            elif fname == "package.json":
                all_deps.extend(parse_package_json(fpath))

    logger.debug("deps_parsed_total", count=len(all_deps))
    return all_deps


def _build_toml_line_map(lines: list[str]) -> dict[str, int]:
    """Construye un mapa nombre_paquete -> numero_de_linea para un TOML."""
    line_map: dict[str, int] = {}
    for i, line in enumerate(lines, 1):
        # Buscar strings que parezcan nombres de paquete en lineas de dependencia
        match = re.search(r'"([a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?)', line)
        if match:
            name = match.group(1).lower()
            if name not in line_map:  # Primera ocurrencia
                line_map[name] = i
    return line_map


def _find_json_key_line(lines: list[str], key: str) -> int:
    """Encuentra el numero de linea de una key en JSON."""
    # Buscar la key con comillas en el JSON
    escaped_key = re.escape(key)
    for i, line in enumerate(lines, 1):
        if re.search(rf'"{escaped_key}"\s*:', line):
            return i
    return 0
