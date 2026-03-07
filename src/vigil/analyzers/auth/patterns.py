"""Patrones regex de auth inseguros para Python (FastAPI/Flask) y JavaScript (Express).

Cada patron es una tupla (compiled_regex, rule_id, framework, description) que se aplica
linea por linea al codigo fuente. Los patrones estan diseñados para minimizar falsos
positivos, por lo que son relativamente especificos a frameworks conocidos.
"""

import re


# ──────────────────────────────────────────────
# AUTH-003: Excessive JWT token lifetime
# ──────────────────────────────────────────────

# Python: jwt.encode con timedelta(hours=N) donde N > threshold
_JWT_TIMEDELTA_HOURS = re.compile(
    r"timedelta\s*\(\s*(?:hours\s*=\s*(\d+)|days\s*=\s*(\d+))",
    re.IGNORECASE,
)

# JavaScript: jwt.sign con expiresIn
_JWT_EXPIRES_IN_JS = re.compile(
    r"""(?:expiresIn|expires_in)\s*[:=]\s*['"](\d+)\s*(h|d|m|s|hr|hrs|hour|hours|day|days)['"]""",
    re.IGNORECASE,
)

# JavaScript: expiresIn as number (seconds)
_JWT_EXPIRES_IN_SECONDS = re.compile(
    r"""(?:expiresIn|expires_in)\s*[:=]\s*(\d+)""",
)

# ──────────────────────────────────────────────
# AUTH-004: Hardcoded JWT secret
# ──────────────────────────────────────────────

# Python: SECRET_KEY = "..." or jwt.encode(..., "string", ...)
_HARDCODED_SECRET_PY = re.compile(
    r"""(?:SECRET_KEY|JWT_SECRET|SECRET|JWT_SECRET_KEY|secret_key|jwt_secret)\s*=\s*['"](.*?)['"]""",
)

# JavaScript: const secret = "..." or jwt.sign(payload, "string")
_HARDCODED_SECRET_JS = re.compile(
    r"""(?:secret|SECRET|secretKey|SECRET_KEY|jwtSecret|JWT_SECRET)\s*[:=]\s*['"](.*?)['"]""",
)

# ──────────────────────────────────────────────
# AUTH-005: CORS allow all origins
# ──────────────────────────────────────────────

# Python FastAPI: CORSMiddleware(allow_origins=["*"])
_CORS_FASTAPI = re.compile(
    r"""allow_origins\s*=\s*\[?\s*['"]?\*['"]?\s*\]?""",
)

# Python Flask-CORS: CORS(app, origins="*") or CORS(app, resources={...: {"origins": "*"}})
_CORS_FLASK = re.compile(
    r"""(?:origins|CORS_ORIGINS)\s*[:=]\s*['"]?\*['"]?""",
)

# JavaScript Express: cors({ origin: '*' }) or cors() without args
_CORS_EXPRESS_STAR = re.compile(
    r"""origin\s*:\s*['"]?\*['"]?""",
)

# Express: cors() with no arguments (allows all by default)
_CORS_EXPRESS_DEFAULT = re.compile(
    r"""(?:app\.use|router\.use)\s*\(\s*cors\s*\(\s*\)\s*\)""",
)

# ──────────────────────────────────────────────
# AUTH-006: Insecure cookie configuration
# ──────────────────────────────────────────────

# Python: set_cookie without secure/httponly/samesite
_COOKIE_SET_PY = re.compile(
    r"""\.set_cookie\s*\(""",
)

# JavaScript: res.cookie without secure/httpOnly/sameSite
_COOKIE_SET_JS = re.compile(
    r"""\.cookie\s*\(""",
)

# Secure flags we look for
_COOKIE_SECURE_FLAG = re.compile(r"""secure\s*[:=]\s*True|secure\s*[:=]\s*true""", re.IGNORECASE)
_COOKIE_HTTPONLY_FLAG = re.compile(
    r"""httponly\s*[:=]\s*True|httpOnly\s*[:=]\s*true|http_only\s*[:=]\s*True""", re.IGNORECASE
)
_COOKIE_SAMESITE_FLAG = re.compile(
    r"""samesite\s*[:=]\s*['"]|sameSite\s*[:=]\s*['"]|same_site\s*[:=]\s*['"]""", re.IGNORECASE
)

# ──────────────────────────────────────────────
# AUTH-007: Password comparison not timing-safe
# ──────────────────────────────────────────────

# Direct password comparison (Python): if password == stored or password != stored
_PW_COMPARE_PY = re.compile(
    r"""(?:password|passwd|pw|pass_word|user_password|hashed_password)\s*[!=]=\s*""",
    re.IGNORECASE,
)

# Direct password comparison (JS): if (password === stored)
_PW_COMPARE_JS = re.compile(
    r"""(?:password|passwd|pw|passWord|userPassword|hashedPassword)\s*[!=]==?\s*""",
    re.IGNORECASE,
)

# Timing-safe comparisons — these indicate correct usage
_TIMING_SAFE = re.compile(
    r"""(?:hmac\.compare_digest|timingSafeEqual|compare_digest|constantTimeCompare|"""
    r"""crypto\.timingSafeEqual|safe_str_cmp|check_password_hash|verify_password|"""
    r"""bcrypt\.check|bcrypt\.compare|argon2\.verify|pbkdf2|scrypt)""",
    re.IGNORECASE,
)


def extract_jwt_lifetime_hours_python(line: str) -> int | None:
    """Extrae el lifetime en horas de un timedelta de Python.

    Retorna None si no se puede extraer.
    """
    match = _JWT_TIMEDELTA_HOURS.search(line)
    if not match:
        return None
    hours_str = match.group(1)
    days_str = match.group(2)
    if hours_str:
        return int(hours_str)
    if days_str:
        return int(days_str) * 24
    return None


def extract_jwt_lifetime_hours_js(line: str) -> int | None:
    """Extrae el lifetime en horas de un expiresIn de JavaScript.

    Retorna None si no se puede extraer.
    """
    match = _JWT_EXPIRES_IN_JS.search(line)
    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()
        if unit in ("h", "hr", "hrs", "hour", "hours"):
            return value
        if unit in ("d", "day", "days"):
            return value * 24
        if unit in ("m",):
            # minutes
            return value // 60 if value >= 60 else 0
        if unit in ("s",):
            return value // 3600 if value >= 3600 else 0
        return None

    # Try numeric seconds
    match = _JWT_EXPIRES_IN_SECONDS.search(line)
    if match:
        seconds = int(match.group(1))
        return seconds // 3600
    return None


def is_cors_allow_all(line: str) -> tuple[bool, str]:
    """Verifica si la linea contiene CORS con allow all.

    Returns:
        (is_cors_all, framework) donde framework es "fastapi", "flask", "express" o "".
    """
    if _CORS_FASTAPI.search(line):
        return True, "fastapi"
    if _CORS_FLASK.search(line):
        return True, "flask"
    if _CORS_EXPRESS_STAR.search(line):
        return True, "express"
    if _CORS_EXPRESS_DEFAULT.search(line):
        return True, "express"
    return False, ""


def is_hardcoded_secret(line: str, is_python: bool) -> str | None:
    """Extrae el valor de un secret hardcodeado si la linea contiene uno.

    Returns:
        El valor del secret hardcodeado o None.
    """
    pattern = _HARDCODED_SECRET_PY if is_python else _HARDCODED_SECRET_JS
    match = pattern.search(line)
    if match:
        value = match.group(1)
        # Ignorar si es una referencia a variable de entorno
        if _is_env_reference(value):
            return None
        # Ignorar strings vacios
        if not value or len(value) < 3:
            return None
        return value
    return None


def _is_env_reference(value: str) -> bool:
    """Verifica si un valor es una referencia a una variable de entorno."""
    env_patterns = [
        r"os\.environ",
        r"os\.getenv",
        r"process\.env",
        r"ENV\[",
        r"\$\{",
        r"config\.",
        r"settings\.",
    ]
    for pattern in env_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            return True
    return False


def has_cookie_security_flags(context_lines: list[str]) -> dict[str, bool]:
    """Verifica si un bloque de codigo tiene flags de seguridad de cookies.

    Examina un bloque de lineas buscando secure, httpOnly, sameSite.
    """
    text = "\n".join(context_lines)
    return {
        "secure": bool(_COOKIE_SECURE_FLAG.search(text)),
        "httponly": bool(_COOKIE_HTTPONLY_FLAG.search(text)),
        "samesite": bool(_COOKIE_SAMESITE_FLAG.search(text)),
    }


def is_password_comparison(line: str, is_python: bool) -> bool:
    """Verifica si la linea contiene una comparacion directa de passwords."""
    pattern = _PW_COMPARE_PY if is_python else _PW_COMPARE_JS
    return bool(pattern.search(line))


def has_timing_safe_comparison(line: str) -> bool:
    """Verifica si la linea usa una comparacion timing-safe."""
    return bool(_TIMING_SAFE.search(line))
