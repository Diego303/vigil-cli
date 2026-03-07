"""AuthAnalyzer — detecta patrones de autenticacion inseguros.

Implementa reglas AUTH-001 a AUTH-007:
  AUTH-001: Endpoint sensible sin auth middleware
  AUTH-002: Endpoint mutante (DELETE/PUT/PATCH/POST) sin auth
  AUTH-003: JWT con lifetime excesivo (>24h por defecto)
  AUTH-004: JWT secret hardcodeado con valor de placeholder o baja entropy
  AUTH-005: CORS configurado con '*' (allow all origins)
  AUTH-006: Cookie sin flags de seguridad (httpOnly, secure, sameSite)
  AUTH-007: Comparacion de passwords sin timing-safe comparison

Estrategia: Pattern matching con regex sobre el codigo fuente.
Soporta Python (FastAPI/Flask) y JavaScript (Express).
"""

import re

import structlog

from vigil.analyzers.auth.endpoint_detector import detect_endpoints
from vigil.analyzers.auth.middleware_checker import check_endpoint_auth
from vigil.analyzers.auth.patterns import (
    extract_jwt_lifetime_hours_js,
    extract_jwt_lifetime_hours_python,
    has_cookie_security_flags,
    has_timing_safe_comparison,
    is_cors_allow_all,
    is_hardcoded_secret,
    is_password_comparison,
)
from vigil.config.schema import AuthConfig, ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity

logger = structlog.get_logger()


class AuthAnalyzer:
    """Analiza codigo para detectar patrones de auth inseguros."""

    @property
    def name(self) -> str:
        return "auth"

    @property
    def category(self) -> Category:
        return Category.AUTH

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        """Ejecuta el analisis de auth patterns."""
        findings: list[Finding] = []
        auth_config = config.auth

        for file_path in files:
            if not _is_relevant_file(file_path):
                continue

            try:
                content = _read_file_safe(file_path)
                if content is None:
                    continue

                is_python = file_path.endswith(".py")

                # AUTH-001/002: Endpoints sin auth
                endpoints = detect_endpoints(content, file_path)
                for ep in endpoints:
                    finding = check_endpoint_auth(
                        ep,
                        require_auth_on_mutating=auth_config.require_auth_on_mutating,
                    )
                    if finding:
                        findings.append(finding)

                # AUTH-003 a AUTH-007: Line-by-line checks
                lines = content.splitlines()
                findings.extend(
                    self._check_lines(lines, file_path, is_python, auth_config)
                )

            except Exception as e:
                logger.warning("auth_file_error", file=file_path, error=str(e))

        return findings

    def _check_lines(
        self,
        lines: list[str],
        file_path: str,
        is_python: bool,
        auth_config: AuthConfig,
    ) -> list[Finding]:
        """Ejecuta checks linea por linea."""
        findings: list[Finding] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            line_num = i + 1

            # Ignorar comentarios
            if _is_comment(stripped, is_python):
                continue

            # AUTH-003: Excessive JWT lifetime
            finding = self._check_jwt_lifetime(
                stripped, file_path, line_num, is_python, auth_config.max_token_lifetime_hours
            )
            if finding:
                findings.append(finding)

            # AUTH-004: Hardcoded JWT secret
            finding = self._check_hardcoded_secret(stripped, file_path, line_num, is_python)
            if finding:
                findings.append(finding)

            # AUTH-005: CORS allow all
            finding = self._check_cors(stripped, file_path, line_num, auth_config)
            if finding:
                findings.append(finding)

            # AUTH-006: Insecure cookies
            finding = self._check_cookie(
                stripped, lines, i, file_path, line_num, is_python
            )
            if finding:
                findings.append(finding)

            # AUTH-007: Password comparison
            finding = self._check_password_comparison(
                stripped, file_path, line_num, is_python
            )
            if finding:
                findings.append(finding)

        return findings

    def _check_jwt_lifetime(
        self,
        line: str,
        file_path: str,
        line_num: int,
        is_python: bool,
        max_hours: int,
    ) -> Finding | None:
        """AUTH-003: Verifica JWT con lifetime excesivo."""
        if is_python:
            hours = extract_jwt_lifetime_hours_python(line)
        else:
            hours = extract_jwt_lifetime_hours_js(line)

        if hours is not None and hours > max_hours:
            return Finding(
                rule_id="AUTH-003",
                category=Category.AUTH,
                severity=Severity.MEDIUM,
                message=(
                    f"JWT with lifetime of {hours} hours "
                    f"(exceeds {max_hours}h threshold)."
                ),
                location=Location(
                    file=file_path,
                    line=line_num,
                    snippet=line.strip(),
                ),
                suggestion=(
                    f"Reduce token lifetime to {max_hours} hours or less, "
                    f"or use refresh tokens for long sessions."
                ),
                metadata={
                    "lifetime_hours": hours,
                    "threshold_hours": max_hours,
                },
            )
        return None

    def _check_hardcoded_secret(
        self,
        line: str,
        file_path: str,
        line_num: int,
        is_python: bool,
    ) -> Finding | None:
        """AUTH-004: Verifica JWT secret hardcodeado."""
        secret_value = is_hardcoded_secret(line, is_python)
        if secret_value is None:
            return None

        # Calcular entropy para determinar si es placeholder o secret real
        from vigil.analyzers.secrets.entropy import shannon_entropy

        entropy = shannon_entropy(secret_value)

        # Solo reportar si la entropy es baja (placeholder/simple) — secrets
        # con alta entropy probablemente son reales y deberian reportarse
        # por el SecretsAnalyzer (SEC-002), pero los de baja entropy son
        # tipicamente generados por AI agents como "supersecret" o "secret123"
        if entropy < 4.0:
            return Finding(
                rule_id="AUTH-004",
                category=Category.AUTH,
                severity=Severity.CRITICAL,
                message=(
                    f"Hardcoded JWT/auth secret with low entropy ({entropy:.1f} bits/char). "
                    f"Value appears to be a placeholder or weak secret."
                ),
                location=Location(
                    file=file_path,
                    line=line_num,
                    snippet=line.strip(),
                ),
                suggestion=(
                    "Use an environment variable for the secret: "
                    "SECRET_KEY = os.environ['SECRET_KEY'] (Python) or "
                    "process.env.SECRET_KEY (JavaScript)."
                ),
                metadata={
                    "entropy": round(entropy, 2),
                    "value_length": len(secret_value),
                },
            )
        return None

    def _check_cors(
        self,
        line: str,
        file_path: str,
        line_num: int,
        auth_config: AuthConfig,
    ) -> Finding | None:
        """AUTH-005: Verifica CORS allow all origins."""
        is_all, framework = is_cors_allow_all(line)
        if not is_all:
            return None

        # Si cors_allow_localhost es True, no reportar si estamos en un
        # contexto de dev (heuristico: nombre de archivo o directorio contiene token)
        if auth_config.cors_allow_localhost:
            import os
            parts = os.path.normpath(file_path).lower().replace("\\", "/").split("/")
            if any(token in part for part in parts for token in ("dev", "test", "local", "example")):
                return None

        return Finding(
            rule_id="AUTH-005",
            category=Category.AUTH,
            severity=Severity.HIGH,
            message=(
                f"CORS configured with '*' allowing requests from any origin "
                f"({framework})."
            ),
            location=Location(
                file=file_path,
                line=line_num,
                snippet=line.strip(),
            ),
            suggestion=(
                "Restrict CORS to specific trusted origins: "
                "allow_origins=['https://yourdomain.com'] (Python) or "
                "origin: 'https://yourdomain.com' (JavaScript)."
            ),
            metadata={
                "framework": framework,
            },
        )

    def _check_cookie(
        self,
        line: str,
        lines: list[str],
        current_idx: int,
        file_path: str,
        line_num: int,
        is_python: bool,
    ) -> Finding | None:
        """AUTH-006: Verifica cookies sin flags de seguridad."""
        # Detectar set_cookie (Python) o .cookie( (JavaScript)
        if is_python:
            if not re.search(r"\.set_cookie\s*\(", line):
                return None
        else:
            if not re.search(r"\.cookie\s*\(", line):
                return None

        # Examinar contexto (la llamada puede ser multilinea)
        start = current_idx
        end = min(len(lines), current_idx + 8)
        context = lines[start:end]

        flags = has_cookie_security_flags(context)
        missing = [k for k, v in flags.items() if not v]

        if not missing:
            return None

        return Finding(
            rule_id="AUTH-006",
            category=Category.AUTH,
            severity=Severity.MEDIUM,
            message=(
                f"Cookie set without security flags: {', '.join(missing)}."
            ),
            location=Location(
                file=file_path,
                line=line_num,
                snippet=line.strip(),
            ),
            suggestion=(
                f"Add missing cookie flags: "
                + ", ".join(f"{f}=True" for f in missing)
                + "."
            ),
            metadata={
                "missing_flags": missing,
            },
        )

    def _check_password_comparison(
        self,
        line: str,
        file_path: str,
        line_num: int,
        is_python: bool,
    ) -> Finding | None:
        """AUTH-007: Verifica comparacion de passwords no timing-safe."""
        if not is_password_comparison(line, is_python):
            return None

        # Si la misma linea tiene una funcion timing-safe, no reportar
        if has_timing_safe_comparison(line):
            return None

        return Finding(
            rule_id="AUTH-007",
            category=Category.AUTH,
            severity=Severity.MEDIUM,
            message=(
                "Password comparison using direct equality operator. "
                "This is vulnerable to timing attacks."
            ),
            location=Location(
                file=file_path,
                line=line_num,
                snippet=line.strip(),
            ),
            suggestion=(
                "Use hmac.compare_digest() (Python) or "
                "crypto.timingSafeEqual() (Node.js) for constant-time comparison."
            ),
        )


def _is_relevant_file(file_path: str) -> bool:
    """Verifica si un archivo es relevante para el analisis de auth."""
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
