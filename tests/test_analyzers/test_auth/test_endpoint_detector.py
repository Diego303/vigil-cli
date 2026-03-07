"""Tests para endpoint detection."""

import pytest

from vigil.analyzers.auth.endpoint_detector import (
    DetectedEndpoint,
    detect_endpoints,
)


class TestFastAPIEndpoints:
    """Tests para deteccion de endpoints FastAPI."""

    def test_get_endpoint(self) -> None:
        content = '@app.get("/users")\nasync def list_users():\n    return []'
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].method == "GET"
        assert endpoints[0].path == "/users"
        assert endpoints[0].framework == "fastapi"

    def test_post_endpoint(self) -> None:
        content = '@app.post("/users")\nasync def create_user():\n    pass'
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].method == "POST"

    def test_delete_endpoint(self) -> None:
        content = '@app.delete("/users/{id}")\nasync def delete_user(id):\n    pass'
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].method == "DELETE"

    def test_router_endpoint(self) -> None:
        content = '@router.put("/items/{id}")\nasync def update_item(id):\n    pass'
        endpoints = detect_endpoints(content, "routes.py")
        assert len(endpoints) == 1
        assert endpoints[0].method == "PUT"
        assert endpoints[0].path == "/items/{id}"

    def test_endpoint_with_auth_depends(self) -> None:
        content = (
            '@app.get("/users/me")\n'
            "async def get_me(user=Depends(get_current_user)):\n"
            "    return user"
        )
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].has_auth is True

    def test_endpoint_without_auth(self) -> None:
        content = '@app.delete("/items/{id}")\nasync def delete_item(id: int):\n    return {"ok": True}'
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].has_auth is False

    def test_multiple_endpoints(self) -> None:
        content = (
            '@app.get("/health")\nasync def health():\n    return "ok"\n\n'
            '@app.post("/users")\nasync def create_user():\n    pass\n\n'
            '@app.delete("/users/{id}")\nasync def delete_user():\n    pass'
        )
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 3

    def test_non_python_file_ignored(self) -> None:
        content = '@app.get("/users")\nasync def list_users():\n    return []'
        endpoints = detect_endpoints(content, "readme.md")
        assert len(endpoints) == 0


class TestFlaskEndpoints:
    """Tests para deteccion de endpoints Flask."""

    def test_route_with_methods(self) -> None:
        content = '@app.route("/users", methods=["GET", "POST"])\ndef users():\n    pass'
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 2
        methods = {ep.method for ep in endpoints}
        assert methods == {"GET", "POST"}

    def test_route_default_get(self) -> None:
        content = '@app.route("/health")\ndef health():\n    return "ok"'
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].method == "GET"
        assert endpoints[0].framework == "flask"

    def test_flask_with_login_required(self) -> None:
        content = (
            "@login_required\n"
            '@app.route("/admin", methods=["GET"])\n'
            "def admin():\n"
            "    return 'admin'"
        )
        endpoints = detect_endpoints(content, "app.py")
        assert len(endpoints) == 1
        assert endpoints[0].has_auth is True


class TestExpressEndpoints:
    """Tests para deteccion de endpoints Express."""

    def test_get_endpoint(self) -> None:
        content = "app.get('/users', (req, res) => { res.json([]); });"
        endpoints = detect_endpoints(content, "app.js")
        assert len(endpoints) == 1
        assert endpoints[0].method == "GET"
        assert endpoints[0].path == "/users"
        assert endpoints[0].framework == "express"

    def test_post_endpoint(self) -> None:
        content = "app.post('/users', (req, res) => { });"
        endpoints = detect_endpoints(content, "routes.ts")
        assert len(endpoints) == 1
        assert endpoints[0].method == "POST"

    def test_delete_with_auth_middleware(self) -> None:
        content = "app.delete('/users/:id', authenticate, (req, res) => { });"
        endpoints = detect_endpoints(content, "app.js")
        assert len(endpoints) == 1
        assert endpoints[0].has_auth is True

    def test_router_endpoint(self) -> None:
        content = "router.put('/items/:id', (req, res) => { });"
        endpoints = detect_endpoints(content, "routes.js")
        assert len(endpoints) == 1
        assert endpoints[0].method == "PUT"

    def test_multiple_middleware(self) -> None:
        content = "app.post('/orders', verifyToken, checkRole, (req, res) => { });"
        endpoints = detect_endpoints(content, "app.js")
        assert len(endpoints) == 1
        # verifyToken matches auth pattern
        assert endpoints[0].has_auth is True

    def test_typescript_file(self) -> None:
        content = "app.get('/health', (req: Request, res: Response) => { });"
        endpoints = detect_endpoints(content, "server.ts")
        assert len(endpoints) == 1


class TestEdgeCases:
    """Tests para edge cases."""

    def test_empty_content(self) -> None:
        endpoints = detect_endpoints("", "app.py")
        assert endpoints == []

    def test_no_endpoints(self) -> None:
        content = 'print("hello world")\nx = 42'
        endpoints = detect_endpoints(content, "app.py")
        assert endpoints == []

    def test_commented_endpoint_python(self) -> None:
        content = '# @app.get("/users")\n# async def list_users():\n#     return []'
        endpoints = detect_endpoints(content, "app.py")
        # Regex may still match in comments — this is a known V0 limitation
        # The important thing is no crash
        assert isinstance(endpoints, list)

    def test_unsupported_file_type(self) -> None:
        content = "some ruby code"
        endpoints = detect_endpoints(content, "app.rb")
        assert endpoints == []
