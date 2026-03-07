"""Detecta valores placeholder en codigo fuente.

Los agentes de IA frecuentemente copian valores de ejemplo de la documentacion
o de .env.example directamente al codigo. Este modulo detecta esos patrones
conocidos como "changeme", "your-api-key-here", "TODO", etc.
"""

import re

# Patrones de placeholder conocidos (regex)
DEFAULT_PLACEHOLDER_PATTERNS: list[str] = [
    r"changeme",
    r"your[-_].*[-_]here",
    r"replace[-_]?me",
    r"insert[-_].*[-_]here",
    r"put[-_].*[-_]here",
    r"add[-_].*[-_]here",
    r"TODO",
    r"FIXME",
    r"xxx+",
    r"sk[-_]your.*",
    r"pk[-_]test[-_].*",
    r"sk[-_]test[-_].*",
    r"sk[-_]live[-_]test.*",
    r"secret123",
    r"password123",
    r"supersecret",
    r"mysecret",
    r"my[-_]?secret[-_]?key",
    r"example\.com",
    r"test[-_]?key",
    r"test[-_]?secret",
    r"dummy[-_]?key",
    r"dummy[-_]?secret",
    r"fake[-_]?key",
    r"fake[-_]?secret",
    r"sample[-_]?key",
    r"sample[-_]?secret",
    r"default[-_]?secret",
    r"default[-_]?key",
    r"placeholder",
]

# Patrones de asignacion de secrets en codigo
_SECRET_ASSIGNMENT_PATTERNS: list[re.Pattern[str]] = [
    # Python: SECRET_KEY = "value", API_KEY = "value", etc.
    re.compile(
        r"""(?:SECRET_KEY|API_KEY|AUTH_TOKEN|ACCESS_TOKEN|PRIVATE_KEY|"""
        r"""DATABASE_URL|DB_PASSWORD|DB_PASS|REDIS_URL|REDIS_PASSWORD|"""
        r"""AWS_SECRET|AWS_ACCESS_KEY|STRIPE_KEY|SENDGRID_KEY|"""
        r"""JWT_SECRET|JWT_KEY|ENCRYPTION_KEY|SIGNING_KEY|"""
        r"""PASSWORD|PASSWD|SECRET|TOKEN|APIKEY|api_key|secret_key|"""
        r"""auth_token|access_token|private_key|database_url|db_password|"""
        r"""jwt_secret|encryption_key|signing_key|password|passwd)\s*=\s*['"](.+?)['"]""",
        re.IGNORECASE,
    ),
    # JavaScript: const secretKey = "value", let apiKey = "value"
    re.compile(
        r"""(?:const|let|var)\s+(?:secretKey|apiKey|authToken|accessToken|"""
        r"""privateKey|databaseUrl|dbPassword|jwtSecret|encryptionKey|"""
        r"""signingKey|password|secret|token|apikey)\s*=\s*['"](.+?)['"]""",
        re.IGNORECASE,
    ),
    # JavaScript/Python object: { secretKey: "value", password: "value" }
    re.compile(
        r"""(?:secret_?[Kk]ey|api_?[Kk]ey|auth_?[Tt]oken|access_?[Tt]oken|"""
        r"""private_?[Kk]ey|database_?[Uu]rl|db_?[Pp]assword|jwt_?[Ss]ecret|"""
        r"""encryption_?[Kk]ey|signing_?[Kk]ey|[Pp]assword|[Pp]asswd)\s*[:=]\s*['"](.+?)['"]""",
    ),
]


def compile_placeholder_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    """Compila una lista de patrones de placeholder en regex."""
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            continue
    return compiled


# Cache compilado de los patrones default (evita recompilar en cada llamada)
_COMPILED_DEFAULT_PATTERNS: list[re.Pattern[str]] = compile_placeholder_patterns(
    DEFAULT_PLACEHOLDER_PATTERNS
)


def is_placeholder_value(value: str, patterns: list[re.Pattern[str]] | None = None) -> bool:
    """Verifica si un valor es un placeholder conocido.

    Args:
        value: Valor a verificar.
        patterns: Lista de patrones compilados. Si None, usa los defaults.

    Returns:
        True si el valor coincide con un patron de placeholder.
    """
    if patterns is None:
        patterns = _COMPILED_DEFAULT_PATTERNS

    for pattern in patterns:
        if pattern.search(value):
            return True
    return False


def find_secret_assignments(
    line: str,
) -> list[str]:
    """Encuentra valores de secrets asignados en una linea de codigo.

    Returns:
        Lista de valores encontrados (puede estar vacia).
    """
    values: list[str] = []
    for pattern in _SECRET_ASSIGNMENT_PATTERNS:
        for match in pattern.finditer(line):
            value = match.group(match.lastindex)
            if value and len(value) >= 3:
                values.append(value)
    return values
