"""Tests para middleware_checker — verificacion de auth en endpoints."""

import pytest

from vigil.analyzers.auth.endpoint_detector import DetectedEndpoint
from vigil.analyzers.auth.middleware_checker import check_endpoint_auth
from vigil.core.finding import Category, Severity


class TestCheckEndpointAuth:
    """Tests para check_endpoint_auth."""

    def test_delete_without_auth(self) -> None:
        """AUTH-002: DELETE sin auth debe generar finding."""
        ep = DetectedEndpoint(
            file="app.py", line=10, method="DELETE", path="/users/{id}",
            framework="fastapi", snippet='@app.delete("/users/{id}")', has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-002"
        assert finding.severity == Severity.HIGH
        assert "DELETE" in finding.message
        assert "/users/{id}" in finding.message

    def test_put_without_auth(self) -> None:
        """AUTH-002: PUT sin auth debe generar finding."""
        ep = DetectedEndpoint(
            file="app.py", line=5, method="PUT", path="/items/{id}",
            framework="express", snippet="app.put('/items/:id', handler)", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-002"

    def test_post_without_auth(self) -> None:
        """AUTH-002: POST sin auth debe generar finding."""
        ep = DetectedEndpoint(
            file="app.py", line=5, method="POST", path="/orders",
            framework="flask", snippet='@app.route("/orders", methods=["POST"])', has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-002"

    def test_delete_with_auth_no_finding(self) -> None:
        """DELETE con auth no debe generar finding."""
        ep = DetectedEndpoint(
            file="app.py", line=10, method="DELETE", path="/users/{id}",
            framework="fastapi", snippet="...", has_auth=True,
        )
        finding = check_endpoint_auth(ep)
        assert finding is None

    def test_get_sensitive_path_without_auth(self) -> None:
        """AUTH-001: GET en path sensible sin auth."""
        ep = DetectedEndpoint(
            file="app.py", line=15, method="GET", path="/admin/dashboard",
            framework="fastapi", snippet='@app.get("/admin/dashboard")', has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-001"
        assert finding.severity == Severity.HIGH

    def test_get_public_path_no_finding(self) -> None:
        """GET en path publico no debe generar finding."""
        ep = DetectedEndpoint(
            file="app.py", line=5, method="GET", path="/health",
            framework="fastapi", snippet='@app.get("/health")', has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is None

    def test_get_user_path_without_auth(self) -> None:
        """AUTH-001: GET /users sin auth."""
        ep = DetectedEndpoint(
            file="app.py", line=20, method="GET", path="/users/profile",
            framework="express", snippet="app.get('/users/profile', handler)", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-001"

    def test_mutating_auth_disabled(self) -> None:
        """Si require_auth_on_mutating=False, no reportar AUTH-002."""
        ep = DetectedEndpoint(
            file="app.py", line=10, method="DELETE", path="/items/{id}",
            framework="fastapi", snippet="...", has_auth=False,
        )
        finding = check_endpoint_auth(ep, require_auth_on_mutating=False)
        assert finding is None

    def test_suggestion_fastapi(self) -> None:
        ep = DetectedEndpoint(
            file="app.py", line=10, method="DELETE", path="/x",
            framework="fastapi", snippet="...", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert "Depends" in finding.suggestion

    def test_suggestion_express(self) -> None:
        ep = DetectedEndpoint(
            file="app.js", line=10, method="DELETE", path="/x",
            framework="express", snippet="...", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert "middleware" in finding.suggestion

    def test_finding_metadata(self) -> None:
        ep = DetectedEndpoint(
            file="app.py", line=10, method="DELETE", path="/users/{id}",
            framework="fastapi", snippet="...", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.metadata["method"] == "DELETE"
        assert finding.metadata["path"] == "/users/{id}"
        assert finding.metadata["framework"] == "fastapi"
        assert finding.category == Category.AUTH
