"""Detecta endpoints HTTP en codigo Python (FastAPI/Flask) y JavaScript (Express).

Usa regex sobre el codigo fuente para encontrar definiciones de endpoints y sus
metodos HTTP. No hace AST parsing — esto es V0, basado en regex.
"""

import re
from dataclasses import dataclass


@dataclass
class DetectedEndpoint:
    """Un endpoint HTTP detectado en el codigo fuente."""

    file: str
    line: int
    method: str          # "GET", "POST", "PUT", "DELETE", "PATCH"
    path: str            # "/users/{id}", "/api/items", etc.
    framework: str       # "fastapi", "flask", "express"
    snippet: str         # Linea de codigo donde se detecto
    has_auth: bool       # Si tiene indicadores de auth


# ──────────────────────────────────────────────
# Patrones de deteccion de endpoints
# ──────────────────────────────────────────────

# FastAPI: @app.get("/path") o @router.post("/path")
_FASTAPI_ENDPOINT = re.compile(
    r"""@(?:\w+)\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]*?)['"]""",
    re.IGNORECASE,
)

# Flask: @app.route("/path", methods=["GET", "POST"])
_FLASK_ROUTE = re.compile(
    r"""@(?:\w+)\.route\s*\(\s*['"]([^'"]*?)['"]""",
    re.IGNORECASE,
)
_FLASK_METHODS = re.compile(
    r"""methods\s*=\s*\[(.*?)\]""",
    re.IGNORECASE,
)

# Express: app.get("/path", handler) o router.post("/path", middleware, handler)
_EXPRESS_ENDPOINT = re.compile(
    r"""(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]*?)['"]""",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────
# Patrones de deteccion de auth middleware
# ──────────────────────────────────────────────

# FastAPI: Depends(get_current_user) o Depends(verify_token) etc.
_FASTAPI_AUTH_DEPENDS = re.compile(
    r"""Depends\s*\(\s*(?:get_current_user|verify_token|require_auth|auth_required|"""
    r"""get_user|check_auth|authenticate|verify_api_key|get_api_key|api_key_auth|"""
    r"""oauth2_scheme|security|HTTPBearer|APIKeyHeader)""",
    re.IGNORECASE,
)

# FastAPI: Security() dependency
_FASTAPI_SECURITY = re.compile(
    r"""Security\s*\(""",
    re.IGNORECASE,
)

# Flask: @login_required, @auth_required, @jwt_required, etc.
_FLASK_AUTH_DECORATOR = re.compile(
    r"""@(?:login_required|auth_required|jwt_required|token_required|"""
    r"""require_auth|requires_auth|permission_required|roles_required|"""
    r"""admin_required|api_key_required|fresh_jwt_required)""",
    re.IGNORECASE,
)

# Express: middleware auth patterns in route args
_EXPRESS_AUTH_MIDDLEWARE = re.compile(
    r"""\b(?:authenticate|isAuthenticated|requireAuth|authMiddleware|verifyToken|"""
    r"""checkAuth|ensureAuth|passport\.authenticate|requireLogin|isLoggedIn|"""
    r"""verifyJWT|authGuard|protect|requireRole|isAdmin|apiKeyAuth|"""
    r"""auth|checkToken|validateToken)\b""",
    re.IGNORECASE,
)


def detect_endpoints(
    content: str,
    file_path: str,
) -> list[DetectedEndpoint]:
    """Detecta endpoints HTTP en el contenido de un archivo.

    Args:
        content: Contenido del archivo fuente.
        file_path: Ruta del archivo (para determinar lenguaje).

    Returns:
        Lista de endpoints detectados.
    """
    is_python = file_path.endswith(".py")
    is_javascript = file_path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))

    if not is_python and not is_javascript:
        return []

    lines = content.splitlines()
    endpoints: list[DetectedEndpoint] = []

    if is_python:
        endpoints.extend(_detect_python_endpoints(lines, file_path))
    elif is_javascript:
        endpoints.extend(_detect_js_endpoints(lines, file_path))

    return endpoints


def _detect_python_endpoints(
    lines: list[str],
    file_path: str,
) -> list[DetectedEndpoint]:
    """Detecta endpoints en codigo Python (FastAPI/Flask)."""
    endpoints: list[DetectedEndpoint] = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # FastAPI/Flask shortcut: @app.get("/path"), @router.post("/path")
        match = _FASTAPI_ENDPOINT.search(stripped)
        if match:
            method = match.group(1).upper()
            path = match.group(2)
            # Buscar auth en el contexto (lineas siguientes del handler)
            context = _get_context_lines(lines, i, window=10)
            has_auth = _python_has_auth(context)
            endpoints.append(DetectedEndpoint(
                file=file_path, line=i + 1, method=method, path=path,
                framework="fastapi", snippet=stripped, has_auth=has_auth,
            ))
            continue

        # Flask: @app.route("/path", methods=["GET"])
        route_match = _FLASK_ROUTE.search(stripped)
        if route_match:
            path = route_match.group(1)
            methods_match = _FLASK_METHODS.search(stripped)
            if methods_match:
                methods_str = methods_match.group(1)
                methods = [m.strip().strip("'\"").upper() for m in methods_str.split(",")]
            else:
                methods = ["GET"]

            # Buscar auth decorators en lineas anteriores y contexto siguiente
            context_before = _get_context_lines(lines, i, window=5, direction="before")
            context_after = _get_context_lines(lines, i, window=10)
            has_auth = _python_has_auth(context_before + context_after)

            for method in methods:
                endpoints.append(DetectedEndpoint(
                    file=file_path, line=i + 1, method=method, path=path,
                    framework="flask", snippet=stripped, has_auth=has_auth,
                ))

    return endpoints


def _detect_js_endpoints(
    lines: list[str],
    file_path: str,
) -> list[DetectedEndpoint]:
    """Detecta endpoints en codigo JavaScript (Express)."""
    endpoints: list[DetectedEndpoint] = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        match = _EXPRESS_ENDPOINT.search(stripped)
        if match:
            method = match.group(1).upper()
            path = match.group(2)
            # Para Express, auth middleware aparece como argumento entre path y handler
            has_auth = bool(_EXPRESS_AUTH_MIDDLEWARE.search(stripped))
            endpoints.append(DetectedEndpoint(
                file=file_path, line=i + 1, method=method, path=path,
                framework="express", snippet=stripped, has_auth=has_auth,
            ))

    return endpoints


def _python_has_auth(context_lines: list[str]) -> bool:
    """Verifica si un bloque de codigo Python tiene indicadores de auth."""
    text = "\n".join(context_lines)
    if _FASTAPI_AUTH_DEPENDS.search(text):
        return True
    if _FASTAPI_SECURITY.search(text):
        return True
    if _FLASK_AUTH_DECORATOR.search(text):
        return True
    return False


def _get_context_lines(
    lines: list[str],
    current_line: int,
    window: int = 10,
    direction: str = "after",
) -> list[str]:
    """Obtiene lineas de contexto alrededor de una posicion."""
    if direction == "before":
        start = max(0, current_line - window)
        return lines[start:current_line + 1]
    else:
        end = min(len(lines), current_line + window + 1)
        return lines[current_line:end]
