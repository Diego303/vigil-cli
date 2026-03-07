"""Tests para AuthAnalyzer completo."""

from pathlib import Path

import pytest

from vigil.analyzers.auth.analyzer import AuthAnalyzer
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "auth"


class TestAuthAnalyzerProtocol:
    """Tests para verificar que AuthAnalyzer cumple el protocolo."""

    def test_name(self) -> None:
        analyzer = AuthAnalyzer()
        assert analyzer.name == "auth"

    def test_category(self) -> None:
        analyzer = AuthAnalyzer()
        assert analyzer.category == Category.AUTH

    def test_analyze_returns_list(self) -> None:
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        result = analyzer.analyze([], config)
        assert isinstance(result, list)
        assert result == []


class TestAuthAnalyzerFastAPI:
    """Tests con fixture FastAPI insegura."""

    def test_detects_cors_allow_all(self, tmp_path: Path) -> None:
        """AUTH-005: CORS con allow_origins=['*']."""
        src = tmp_path / "app.py"
        src.write_text('app.add_middleware(CORSMiddleware, allow_origins=["*"])\n')

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)

        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) >= 1
        assert "CORS" in auth005[0].message
        assert "*" in auth005[0].message

    def test_detects_hardcoded_secret(self, tmp_path: Path) -> None:
        """AUTH-004: Secret hardcodeado con baja entropy."""
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "supersecret123"\n')

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1
        assert auth004[0].severity == Severity.CRITICAL
        assert "entropy" in auth004[0].message.lower()

    def test_detects_excessive_jwt_lifetime(self, tmp_path: Path) -> None:
        """AUTH-003: JWT con lifetime >24h."""
        src = tmp_path / "app.py"
        src.write_text(
            'from datetime import timedelta\n'
            'exp = timedelta(hours=72)\n'
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 24
        findings = analyzer.analyze([str(src)], config)

        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) >= 1
        assert "72 hours" in auth003[0].message
        assert auth003[0].severity == Severity.MEDIUM

    def test_detects_unprotected_delete(self, tmp_path: Path) -> None:
        """AUTH-002: DELETE endpoint sin auth."""
        src = tmp_path / "app.py"
        src.write_text(
            '@app.delete("/users/{user_id}")\n'
            "async def delete_user(user_id: int):\n"
            "    return {'deleted': user_id}\n"
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth002 = [f for f in findings if f.rule_id == "AUTH-002"]
        assert len(auth002) >= 1
        assert "DELETE" in auth002[0].message

    def test_detects_sensitive_path_without_auth(self, tmp_path: Path) -> None:
        """AUTH-001: GET /admin sin auth."""
        src = tmp_path / "app.py"
        src.write_text(
            '@app.get("/admin/dashboard")\n'
            "async def admin():\n"
            "    return {'data': 'secret'}\n"
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth001 = [f for f in findings if f.rule_id == "AUTH-001"]
        assert len(auth001) >= 1

    def test_detects_cookie_without_flags(self, tmp_path: Path) -> None:
        """AUTH-006: Cookie sin flags de seguridad."""
        src = tmp_path / "app.py"
        src.write_text(
            'response.set_cookie("session", "abc123")\n'
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth006 = [f for f in findings if f.rule_id == "AUTH-006"]
        assert len(auth006) >= 1
        assert auth006[0].severity == Severity.MEDIUM

    def test_detects_password_comparison(self, tmp_path: Path) -> None:
        """AUTH-007: Comparacion directa de passwords."""
        src = tmp_path / "app.py"
        src.write_text(
            'if password == stored_password:\n'
            '    return True\n'
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth007 = [f for f in findings if f.rule_id == "AUTH-007"]
        assert len(auth007) >= 1
        assert "timing" in auth007[0].message.lower()


class TestAuthAnalyzerExpress:
    """Tests con codigo Express."""

    def test_detects_cors_default(self, tmp_path: Path) -> None:
        """AUTH-005: cors() sin opciones en Express."""
        src = tmp_path / "app.js"
        src.write_text("app.use(cors())\n")

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)

        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) >= 1

    def test_detects_js_jwt_lifetime(self, tmp_path: Path) -> None:
        """AUTH-003: JWT expiresIn en JS."""
        src = tmp_path / "app.js"
        src.write_text(
            "const token = jwt.sign(payload, secret, { expiresIn: '72h' });\n"
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 24
        findings = analyzer.analyze([str(src)], config)

        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) >= 1
        assert "72 hours" in auth003[0].message

    def test_detects_express_delete_no_auth(self, tmp_path: Path) -> None:
        """AUTH-002: DELETE sin auth en Express."""
        src = tmp_path / "app.js"
        src.write_text(
            "app.delete('/users/:id', (req, res) => { res.json({}); });\n"
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth002 = [f for f in findings if f.rule_id == "AUTH-002"]
        assert len(auth002) >= 1


class TestAuthAnalyzerNegative:
    """Tests negativos — codigo seguro NO debe generar findings."""

    def test_secure_app_no_findings(self, tmp_path: Path) -> None:
        """App segura no genera findings de auth."""
        src = tmp_path / "app.py"
        src.write_text(
            "import os\n"
            "SECRET_KEY = os.environ['SECRET_KEY']\n"
            '@app.delete("/users/{id}")\n'
            "async def delete_user(id: int, user=Depends(get_current_user)):\n"
            "    return {'deleted': id}\n"
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        # No AUTH-002 because endpoint has Depends(get_current_user)
        auth002 = [f for f in findings if f.rule_id == "AUTH-002"]
        assert len(auth002) == 0

        # No AUTH-004 because SECRET_KEY is from env var (assignment is os.environ)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) == 0

    def test_jwt_within_threshold(self, tmp_path: Path) -> None:
        """JWT con lifetime dentro del threshold no genera finding."""
        src = tmp_path / "app.py"
        src.write_text("exp = timedelta(hours=1)\n")

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 24
        findings = analyzer.analyze([str(src)], config)

        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) == 0

    def test_specific_cors_origins(self, tmp_path: Path) -> None:
        """CORS con origenes especificos no genera finding."""
        src = tmp_path / "app.py"
        src.write_text(
            'app.add_middleware(CORSMiddleware, allow_origins=["https://myapp.com"])\n'
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) == 0

    def test_cors_in_dev_file_with_allow_localhost(self, tmp_path: Path) -> None:
        """CORS * en archivo dev no genera finding si cors_allow_localhost=True."""
        src = tmp_path / "dev_config.py"
        src.write_text('allow_origins=["*"]\n')

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = True  # Default
        findings = analyzer.analyze([str(src)], config)

        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) == 0

    def test_public_get_endpoint_no_finding(self, tmp_path: Path) -> None:
        """GET en path publico sin auth no genera finding."""
        src = tmp_path / "app.py"
        src.write_text(
            '@app.get("/health")\nasync def health():\n    return "ok"\n'
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        assert len(findings) == 0

    def test_non_code_files_ignored(self) -> None:
        """Archivos no-codigo son ignorados."""
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze(["/some/readme.md", "/some/data.json"], config)
        assert findings == []


class TestAuthAnalyzerEdgeCases:
    """Tests para edge cases."""

    def test_empty_file(self, tmp_path: Path) -> None:
        src = tmp_path / "empty.py"
        src.write_text("")

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert findings == []

    def test_nonexistent_file(self) -> None:
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze(["/nonexistent/file.py"], config)
        assert findings == []

    def test_binary_file_handled(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        # Should not crash
        findings = analyzer.analyze([str(src)], config)
        assert isinstance(findings, list)

    def test_comments_ignored(self, tmp_path: Path) -> None:
        """Lineas de comentario no deben generar findings."""
        src = tmp_path / "app.py"
        src.write_text(
            '# SECRET_KEY = "supersecret"\n'
            '# allow_origins=["*"]\n'
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        # Comments should be ignored
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth004) == 0
        assert len(auth005) == 0

    def test_js_comments_ignored(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "// const secret = 'supersecret123';\n"
            "// origin: '*'\n"
        )

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)

        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth004) == 0
        assert len(auth005) == 0

    def test_fixture_insecure_fastapi(self) -> None:
        """Integration test con fixture FastAPI insegura."""
        fixture = FIXTURES_DIR / "insecure_fastapi.py"
        if not fixture.exists():
            pytest.skip("Fixture not found")

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(fixture)], config)

        rule_ids = {f.rule_id for f in findings}
        # Should detect multiple issues
        assert "AUTH-005" in rule_ids  # CORS
        assert "AUTH-004" in rule_ids  # Hardcoded secret
        assert "AUTH-003" in rule_ids  # JWT lifetime

    def test_fixture_secure_app(self) -> None:
        """Integration test con fixture segura."""
        fixture = FIXTURES_DIR / "secure_app.py"
        if not fixture.exists():
            pytest.skip("Fixture not found")

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(fixture)], config)

        # Secure app should have minimal/no auth findings
        # (env var for secret, specific CORS origins, normal lifetime)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth004) == 0
        assert len(auth005) == 0
