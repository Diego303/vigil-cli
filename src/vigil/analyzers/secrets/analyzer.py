"""SecretsAnalyzer — detecta secrets mal gestionados en codigo.

Implementa reglas SEC-001 a SEC-006:
  SEC-001: Valor placeholder en codigo (copiado de docs o .env.example)
  SEC-002: Secret hardcodeado con baja entropy (generado por AI agent)
  SEC-003: Connection string con credenciales embebidas
  SEC-004: Variable de entorno sensible con valor default en codigo
  SEC-005: (Reservado — file not in gitignore, requiere analisis de .gitignore)
  SEC-006: Valor copiado textualmente de .env.example

Estrategia: Regex + entropy analysis + env example tracing.
"""

import re
from pathlib import Path

import structlog

from vigil.analyzers.secrets.entropy import shannon_entropy
from vigil.analyzers.secrets.env_tracer import (
    find_env_example_files,
    find_env_values_in_code,
    parse_env_example,
    EnvExampleEntry,
)
from vigil.analyzers.secrets.placeholder_detector import (
    compile_placeholder_patterns,
    find_secret_assignments,
    is_placeholder_value,
)
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity

logger = structlog.get_logger()

# Connection string patterns con credenciales embebidas
_CONNECTION_STRING_PATTERNS: list[re.Pattern[str]] = [
    # postgresql://user:password@host/db or redis://:password@host
    re.compile(
        r"""(?:postgresql|postgres|mysql|mariadb|mongodb|redis|amqp|rabbitmq)"""
        r"""://([^:]*):([^@]+)@""",
        re.IGNORECASE,
    ),
    # mongodb+srv://user:password@host
    re.compile(
        r"""mongodb\+srv://([^:]+):([^@]+)@""",
        re.IGNORECASE,
    ),
    # sqlserver://user:password@host
    re.compile(
        r"""(?:sqlserver|mssql)://([^:]+):([^@]+)@""",
        re.IGNORECASE,
    ),
]

# Patrones de variables de entorno con defaults
_ENV_DEFAULT_PATTERNS: list[re.Pattern[str]] = [
    # Python: os.environ.get("KEY", "default") or os.getenv("KEY", "default")
    re.compile(
        r"""os\.(?:environ\.get|getenv)\s*\(\s*['"]"""
        r"""((?:SECRET|KEY|TOKEN|PASSWORD|PASSWD|API_KEY|AUTH|JWT|"""
        r"""DATABASE_URL|DB_PASS|PRIVATE_KEY|ENCRYPTION|SIGNING|STRIPE|AWS)[^'"]*?)"""
        r"""['"]\s*,\s*['"](.+?)['"]""",
        re.IGNORECASE,
    ),
    # JavaScript: process.env.KEY || "default"
    re.compile(
        r"""process\.env\.([A-Z_]*(?:SECRET|KEY|TOKEN|PASSWORD|PASSWD|API_KEY|AUTH|JWT|"""
        r"""DATABASE_URL|DB_PASS|PRIVATE_KEY|ENCRYPTION|SIGNING|STRIPE|AWS)[A-Z_]*)"""
        r"""\s*\|\|\s*['"](.+?)['"]""",
        re.IGNORECASE,
    ),
    # JavaScript: process.env["KEY"] || "default"
    re.compile(
        r"""process\.env\[['"]([^'"]*(?:SECRET|KEY|TOKEN|PASSWORD|PASSWD|API_KEY|AUTH|JWT)[^'"]*?)"""
        r"""['"]\]\s*\|\|\s*['"](.+?)['"]""",
        re.IGNORECASE,
    ),
]


class SecretsAnalyzer:
    """Analiza codigo para detectar secrets mal gestionados."""

    @property
    def name(self) -> str:
        return "secrets"

    @property
    def category(self) -> Category:
        return Category.SECRETS

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        """Ejecuta el analisis de secrets."""
        findings: list[Finding] = []
        secrets_config = config.secrets

        # Compilar patrones de placeholder
        placeholder_patterns = compile_placeholder_patterns(
            secrets_config.placeholder_patterns
        )

        # Cargar entradas de .env.example si check_env_example esta habilitado
        env_entries: list[EnvExampleEntry] = []
        if secrets_config.check_env_example:
            env_entries = self._load_env_examples(files)
            if env_entries:
                logger.debug("env_example_loaded", entries=len(env_entries))

        for file_path in files:
            if not _is_relevant_file(file_path):
                continue

            try:
                content = _read_file_safe(file_path)
                if content is None:
                    continue

                # SEC-006: Buscar valores de .env.example en el codigo
                if env_entries:
                    findings.extend(
                        self._check_env_values(content, file_path, env_entries)
                    )

                # SEC-001, SEC-002, SEC-003, SEC-004: Checks linea por linea
                lines = content.splitlines()
                findings.extend(
                    self._check_lines(
                        lines, file_path, secrets_config.min_entropy, placeholder_patterns
                    )
                )

            except Exception as e:
                logger.warning("secrets_file_error", file=file_path, error=str(e))

        return findings

    def _load_env_examples(self, files: list[str]) -> list[EnvExampleEntry]:
        """Carga entradas de archivos .env.example encontrados en las raices."""
        entries: list[EnvExampleEntry] = []
        roots_seen: set[str] = set()

        for f in files:
            p = Path(f)
            root = str(p.parent if p.is_file() else p)
            if root in roots_seen:
                continue
            roots_seen.add(root)

            env_files = find_env_example_files(root)
            for env_file in env_files:
                entries.extend(parse_env_example(env_file))

        return entries

    def _check_env_values(
        self,
        content: str,
        file_path: str,
        env_entries: list[EnvExampleEntry],
    ) -> list[Finding]:
        """SEC-006: Busca valores copiados de .env.example."""
        findings: list[Finding] = []

        matches = find_env_values_in_code(content, env_entries)
        for line_num, entry in matches:
            findings.append(Finding(
                rule_id="SEC-006",
                category=Category.SECRETS,
                severity=Severity.CRITICAL,
                message=(
                    f"Value from {Path(entry.file).name} "
                    f"(key: {entry.key}) appears copied into source code."
                ),
                location=Location(
                    file=file_path,
                    line=line_num,
                ),
                suggestion=(
                    f"Use os.environ.get('{entry.key}') (Python) or "
                    f"process.env.{entry.key} (JavaScript) instead of "
                    f"hardcoding the value."
                ),
                metadata={
                    "env_key": entry.key,
                    "env_file": str(Path(entry.file).name),
                },
            ))

        return findings

    def _check_lines(
        self,
        lines: list[str],
        file_path: str,
        min_entropy: float,
        placeholder_patterns: list[re.Pattern[str]],
    ) -> list[Finding]:
        """Ejecuta checks linea por linea para SEC-001 a SEC-004."""
        findings: list[Finding] = []
        is_python = file_path.endswith(".py")

        for i, line in enumerate(lines):
            stripped = line.strip()
            line_num = i + 1

            # Ignorar comentarios
            if _is_comment(stripped, is_python):
                continue

            # SEC-003: Connection strings con credenciales
            finding = self._check_connection_string(stripped, file_path, line_num)
            if finding:
                findings.append(finding)
                continue  # No duplicar con SEC-001/002

            # SEC-004: Env var con default sensible
            finding = self._check_env_default(stripped, file_path, line_num, min_entropy)
            if finding:
                findings.append(finding)
                continue

            # SEC-001 / SEC-002: Secret assignments
            secret_values = find_secret_assignments(stripped)
            for value in secret_values:
                # SEC-001: Placeholder
                if is_placeholder_value(value, placeholder_patterns):
                    findings.append(Finding(
                        rule_id="SEC-001",
                        category=Category.SECRETS,
                        severity=Severity.CRITICAL,
                        message=(
                            f"Hardcoded secret appears to be a placeholder value: "
                            f"'{_truncate(value, 40)}'."
                        ),
                        location=Location(
                            file=file_path,
                            line=line_num,
                            snippet=stripped,
                        ),
                        suggestion=(
                            "Replace with an environment variable. "
                            "Never commit placeholder secrets to the repository."
                        ),
                        metadata={
                            "value_preview": _truncate(value, 20),
                        },
                    ))
                    break  # Solo un finding por linea

                # SEC-002: Low-entropy hardcoded secret
                entropy = shannon_entropy(value)
                if entropy < min_entropy and len(value) >= 6:
                    findings.append(Finding(
                        rule_id="SEC-002",
                        category=Category.SECRETS,
                        severity=Severity.CRITICAL,
                        message=(
                            f"Hardcoded secret with low entropy "
                            f"({entropy:.1f} bits/char). "
                            f"Likely a weak or AI-generated placeholder."
                        ),
                        location=Location(
                            file=file_path,
                            line=line_num,
                            snippet=stripped,
                        ),
                        suggestion=(
                            "Use a strong, randomly generated secret stored "
                            "in an environment variable."
                        ),
                        metadata={
                            "entropy": round(entropy, 2),
                            "value_length": len(value),
                        },
                    ))
                    break  # Solo un finding por linea

        return findings

    def _check_connection_string(
        self,
        line: str,
        file_path: str,
        line_num: int,
    ) -> Finding | None:
        """SEC-003: Detecta connection strings con credenciales embebidas."""
        for pattern in _CONNECTION_STRING_PATTERNS:
            match = pattern.search(line)
            if match:
                user = match.group(1)
                password = match.group(2)
                # Ignorar si user/password son referencias a env vars
                if "$" in password or "%" in password:
                    continue
                return Finding(
                    rule_id="SEC-003",
                    category=Category.SECRETS,
                    severity=Severity.CRITICAL,
                    message=(
                        f"Connection string with embedded credentials detected."
                    ),
                    location=Location(
                        file=file_path,
                        line=line_num,
                        snippet=_redact_password(line.strip()),
                    ),
                    suggestion=(
                        "Move credentials to environment variables and construct "
                        "the connection string at runtime."
                    ),
                    metadata={
                        "username": user,
                    },
                )
        return None

    def _check_env_default(
        self,
        line: str,
        file_path: str,
        line_num: int,
        min_entropy: float,
    ) -> Finding | None:
        """SEC-004: Detecta env vars sensibles con valores default."""
        for pattern in _ENV_DEFAULT_PATTERNS:
            match = pattern.search(line)
            if match:
                key = match.group(1)
                default_value = match.group(2)

                # Ignorar si el default es vacio o muy corto
                if not default_value or len(default_value) < 3:
                    continue

                return Finding(
                    rule_id="SEC-004",
                    category=Category.SECRETS,
                    severity=Severity.HIGH,
                    message=(
                        f"Sensitive environment variable '{key}' has a hardcoded "
                        f"default value."
                    ),
                    location=Location(
                        file=file_path,
                        line=line_num,
                        snippet=line.strip(),
                    ),
                    suggestion=(
                        f"Remove the default value and require '{key}' to be set "
                        f"in the environment. Fail explicitly if missing."
                    ),
                    metadata={
                        "env_key": key,
                        "default_length": len(default_value),
                    },
                )
        return None


def _is_relevant_file(file_path: str) -> bool:
    """Verifica si un archivo es relevante para el analisis de secrets."""
    return file_path.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))


def _is_comment(line: str, is_python: bool) -> bool:
    """Verifica si una linea es un comentario."""
    if is_python:
        return line.startswith("#")
    return line.startswith("//")


def _read_file_safe(file_path: str) -> str | None:
    """Lee un archivo de forma segura, retornando None si no se puede leer."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IOError):
        return None


def _truncate(value: str, max_len: int) -> str:
    """Trunca un valor para mostrar en mensajes."""
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def _redact_password(line: str) -> str:
    """Redacta passwords en connection strings para snippets seguros."""
    # Reemplazar password entre :// y @ con ***
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", line)
