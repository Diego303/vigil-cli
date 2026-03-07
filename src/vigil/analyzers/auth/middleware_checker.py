"""Verifica que endpoints sensibles tienen auth middleware.

Determina cuales endpoints son "sensibles" (mutantes o manejan datos sensibles)
y verifica que tienen algun indicador de autenticacion/autorizacion.
"""

from vigil.analyzers.auth.endpoint_detector import DetectedEndpoint
from vigil.core.finding import Category, Finding, Location, Severity


# Metodos HTTP que mutan estado — requieren auth
MUTATING_METHODS: set[str] = {"POST", "PUT", "DELETE", "PATCH"}

# Paths sensibles que siempre requieren auth
SENSITIVE_PATH_PATTERNS: list[str] = [
    "/admin",
    "/user",
    "/users",
    "/account",
    "/profile",
    "/settings",
    "/billing",
    "/payment",
    "/order",
    "/api/v",
    "/private",
    "/internal",
    "/dashboard",
]


def check_endpoint_auth(
    endpoint: DetectedEndpoint,
    require_auth_on_mutating: bool = True,
) -> Finding | None:
    """Verifica si un endpoint necesita auth y no lo tiene.

    Args:
        endpoint: Endpoint detectado.
        require_auth_on_mutating: Si se requiere auth en metodos mutantes.

    Returns:
        Finding si el endpoint no tiene auth y deberia, None en caso contrario.
    """
    if endpoint.has_auth:
        return None

    is_mutating = endpoint.method in MUTATING_METHODS
    is_sensitive_path = _is_sensitive_path(endpoint.path)

    # AUTH-002: Endpoint mutante sin auth
    if is_mutating and require_auth_on_mutating:
        return Finding(
            rule_id="AUTH-002",
            category=Category.AUTH,
            severity=Severity.HIGH,
            message=(
                f"{endpoint.method} endpoint '{endpoint.path}' has no authentication "
                f"or authorization middleware ({endpoint.framework})."
            ),
            location=Location(
                file=endpoint.file,
                line=endpoint.line,
                snippet=endpoint.snippet,
            ),
            suggestion=_get_auth_suggestion(endpoint.framework, endpoint.method),
            metadata={
                "method": endpoint.method,
                "path": endpoint.path,
                "framework": endpoint.framework,
            },
        )

    # AUTH-001: Endpoint con path sensible sin auth
    if is_sensitive_path and not is_mutating:
        return Finding(
            rule_id="AUTH-001",
            category=Category.AUTH,
            severity=Severity.HIGH,
            message=(
                f"Sensitive endpoint '{endpoint.method} {endpoint.path}' "
                f"has no authentication middleware ({endpoint.framework})."
            ),
            location=Location(
                file=endpoint.file,
                line=endpoint.line,
                snippet=endpoint.snippet,
            ),
            suggestion=_get_auth_suggestion(endpoint.framework, endpoint.method),
            metadata={
                "method": endpoint.method,
                "path": endpoint.path,
                "framework": endpoint.framework,
            },
        )

    return None


def _is_sensitive_path(path: str) -> bool:
    """Verifica si un path es sensible."""
    path_lower = path.lower()
    return any(pattern in path_lower for pattern in SENSITIVE_PATH_PATTERNS)


def _get_auth_suggestion(framework: str, method: str) -> str:
    """Genera una sugerencia de correccion segun el framework."""
    suggestions = {
        "fastapi": (
            f"Add authentication dependency: "
            f"async def handler(..., user: User = Depends(get_current_user))"
        ),
        "flask": (
            f"Add @login_required decorator or verify authentication "
            f"in the {method} handler."
        ),
        "express": (
            f"Add authentication middleware before the handler: "
            f"app.{method.lower()}('/path', authenticate, handler)"
        ),
    }
    return suggestions.get(framework, "Add authentication middleware to this endpoint.")
