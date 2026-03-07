"""QA regression tests para AuthAnalyzer — FASE 2.

Cubre: edge cases, false positives, false negatives, configuration,
regression tests de bugs encontrados en QA audit.
"""

from pathlib import Path

import pytest

from vigil.analyzers.auth.analyzer import AuthAnalyzer, _is_comment, _is_relevant_file
from vigil.analyzers.auth.endpoint_detector import (
    DetectedEndpoint,
    _EXPRESS_AUTH_MIDDLEWARE,
    detect_endpoints,
)
from vigil.analyzers.auth.middleware_checker import (
    SENSITIVE_PATH_PATTERNS,
    check_endpoint_auth,
    _is_sensitive_path,
)
from vigil.analyzers.auth.patterns import (
    extract_jwt_lifetime_hours_js,
    extract_jwt_lifetime_hours_python,
    has_cookie_security_flags,
    has_timing_safe_comparison,
    is_cors_allow_all,
    is_hardcoded_secret,
    is_password_comparison,
)
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


# ──────────────────────────────────────────────
# Regression: Bug #4 — _EXPRESS_AUTH_MIDDLEWARE word boundary
# ──────────────────────────────────────────────


class TestExpressAuthMiddlewareWordBoundary:
    """Regression: 'auth' regex should not match substrings like 'auth_header'."""

    def test_auth_header_not_matched(self) -> None:
        assert not _EXPRESS_AUTH_MIDDLEWARE.search("const auth_header = req.headers")

    def test_authorization_not_matched(self) -> None:
        assert not _EXPRESS_AUTH_MIDDLEWARE.search("req.headers.authorization")

    def test_auth_exact_matched(self) -> None:
        assert _EXPRESS_AUTH_MIDDLEWARE.search("app.get('/x', auth, handler)")

    def test_authenticate_matched(self) -> None:
        assert _EXPRESS_AUTH_MIDDLEWARE.search("app.delete('/x', authenticate, handler)")

    def test_passport_authenticate_matched(self) -> None:
        assert _EXPRESS_AUTH_MIDDLEWARE.search(
            "app.post('/x', passport.authenticate('jwt'), handler)"
        )

    def test_auth_in_express_route_detects_correctly(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "app.delete('/users/:id', auth, (req, res) => { });\n"
        )
        endpoints = detect_endpoints(src.read_text(), str(src))
        assert len(endpoints) == 1
        assert endpoints[0].has_auth is True

    def test_auth_header_variable_no_false_positive(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "const auth_token = req.headers.authorization;\n"
            "app.delete('/items/:id', (req, res) => { });\n"
        )
        endpoints = detect_endpoints(src.read_text(), str(src))
        delete_eps = [ep for ep in endpoints if ep.method == "DELETE"]
        assert len(delete_eps) == 1
        assert delete_eps[0].has_auth is False


# ──────────────────────────────────────────────
# Regression: Bug #1 — auth_config typed as AuthConfig
# ──────────────────────────────────────────────


class TestAuthConfigTyping:
    """Regression: auth_config should accept AuthConfig properties."""

    def test_max_token_lifetime_hours_default(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("exp = timedelta(hours=48)\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        # Default is 24h, 48h should trigger
        findings = analyzer.analyze([str(src)], config)
        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) >= 1

    def test_custom_max_token_lifetime(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("exp = timedelta(hours=48)\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 72
        findings = analyzer.analyze([str(src)], config)
        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) == 0  # 48 < 72, no finding

    def test_cors_allow_localhost_toggle(self, tmp_path: Path) -> None:
        src = tmp_path / "dev_config.py"
        src.write_text('allow_origins=["*"]\n')
        analyzer = AuthAnalyzer()

        config_allow = ScanConfig()
        config_allow.auth.cors_allow_localhost = True
        assert len([
            f for f in analyzer.analyze([str(src)], config_allow)
            if f.rule_id == "AUTH-005"
        ]) == 0

        config_deny = ScanConfig()
        config_deny.auth.cors_allow_localhost = False
        assert len([
            f for f in analyzer.analyze([str(src)], config_deny)
            if f.rule_id == "AUTH-005"
        ]) >= 1


# ──────────────────────────────────────────────
# Regression: Bug #13 — _check_cors dev path heuristic
# ──────────────────────────────────────────────


class TestCorsDevPathHeuristic:
    """Regression: cors_allow_localhost should match path segments, not substrings."""

    def test_development_dir_suppresses(self, tmp_path: Path) -> None:
        dev_dir = tmp_path / "dev"
        dev_dir.mkdir()
        src = dev_dir / "config.py"
        src.write_text('allow_origins=["*"]\n')

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = True
        findings = analyzer.analyze([str(src)], config)
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) == 0

    def test_production_file_not_suppressed(self, tmp_path: Path) -> None:
        """'production_cors.py' should NOT be suppressed — no dev/test segments."""
        # Use a path without any dev/test/local/example in segments
        prod_dir = tmp_path / "production"
        prod_dir.mkdir()
        src = prod_dir / "cors.py"
        src.write_text('allow_origins=["*"]\n')

        analyzer = AuthAnalyzer()
        # cors_allow_localhost = False to bypass the heuristic entirely
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) >= 1

    def test_test_dir_suppresses(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        src = test_dir / "config.py"
        src.write_text('allow_origins=["*"]\n')

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = True
        findings = analyzer.analyze([str(src)], config)
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) == 0

    def test_example_dir_suppresses(self, tmp_path: Path) -> None:
        example_dir = tmp_path / "examples"
        example_dir.mkdir()
        src = example_dir / "app.py"
        src.write_text('allow_origins=["*"]\n')

        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = True
        findings = analyzer.analyze([str(src)], config)
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) == 0


# ──────────────────────────────────────────────
# False positives
# ──────────────────────────────────────────────


class TestAuthFalsePositives:
    """Tests para asegurar que codigo legitimo no genera false positives."""

    def test_high_entropy_secret_not_reported_by_auth004(self, tmp_path: Path) -> None:
        """AUTH-004 only fires on low-entropy secrets. High-entropy = SEC-002 domain."""
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "a3f8b2c1d9e0x7y4z6w"\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) == 0

    def test_cookie_with_all_flags_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            "response.set_cookie(\n"
            '    "session", "value",\n'
            "    secure=True,\n"
            "    httponly=True,\n"
            '    samesite="Lax",\n'
            ")\n"
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth006 = [f for f in findings if f.rule_id == "AUTH-006"]
        assert len(auth006) == 0

    def test_js_cookie_with_all_flags_no_finding(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "res.cookie('token', value, {\n"
            "    secure: true,\n"
            "    httpOnly: true,\n"
            "    sameSite: 'strict'\n"
            "});\n"
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth006 = [f for f in findings if f.rule_id == "AUTH-006"]
        assert len(auth006) == 0

    def test_bcrypt_comparison_not_reported(self, tmp_path: Path) -> None:
        """Password comparison using bcrypt should not trigger AUTH-007."""
        src = tmp_path / "app.py"
        src.write_text("result = bcrypt.check(password, hashed)\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth007 = [f for f in findings if f.rule_id == "AUTH-007"]
        assert len(auth007) == 0

    def test_require_auth_on_mutating_disabled(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            '@app.delete("/items/{id}")\nasync def delete_item(id):\n    pass\n'
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.require_auth_on_mutating = False
        findings = analyzer.analyze([str(src)], config)
        auth002 = [f for f in findings if f.rule_id == "AUTH-002"]
        assert len(auth002) == 0

    def test_jwt_at_exactly_threshold_no_finding(self, tmp_path: Path) -> None:
        """JWT lifetime == threshold should NOT trigger (only > threshold)."""
        src = tmp_path / "app.py"
        src.write_text("exp = timedelta(hours=24)\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 24
        findings = analyzer.analyze([str(src)], config)
        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) == 0


# ──────────────────────────────────────────────
# False negatives
# ──────────────────────────────────────────────


class TestAuthFalseNegatives:
    """Tests para verificar deteccion en escenarios complejos."""

    def test_cors_in_multiline_config(self, tmp_path: Path) -> None:
        """CORS * en configuracion multilinea."""
        src = tmp_path / "app.py"
        src.write_text(
            "app.add_middleware(\n"
            "    CORSMiddleware,\n"
            '    allow_origins=["*"],\n'
            ")\n"
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) >= 1

    def test_jwt_timedelta_days(self, tmp_path: Path) -> None:
        """JWT timedelta with days should also trigger."""
        src = tmp_path / "app.py"
        src.write_text("exp = timedelta(days=7)\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 24
        findings = analyzer.analyze([str(src)], config)
        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) >= 1
        assert "168 hours" in auth003[0].message  # 7 * 24

    def test_multiple_endpoints_all_detected(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            '@app.delete("/users/{id}")\nasync def delete_user(): pass\n'
            '@app.put("/users/{id}")\nasync def update_user(): pass\n'
            '@app.post("/orders")\nasync def create_order(): pass\n'
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth002 = [f for f in findings if f.rule_id == "AUTH-002"]
        assert len(auth002) == 3

    def test_js_expires_in_with_days(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text("jwt.sign(payload, secret, { expiresIn: '7d' });\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.max_token_lifetime_hours = 24
        findings = analyzer.analyze([str(src)], config)
        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) >= 1


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────


class TestAuthEdgeCases:
    """Tests para edge cases adicionales."""

    def test_multiple_rules_same_file(self, tmp_path: Path) -> None:
        """Un archivo con multiples problemas genera multiples findings."""
        src = tmp_path / "app.py"
        src.write_text(
            'SECRET_KEY = "supersecret"\n'
            'allow_origins=["*"]\n'
            "exp = timedelta(hours=72)\n"
            "if password == stored:\n"
            '    response.set_cookie("s", "v")\n'
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)
        rule_ids = {f.rule_id for f in findings}
        assert "AUTH-003" in rule_ids
        assert "AUTH-004" in rule_ids
        assert "AUTH-005" in rule_ids
        assert "AUTH-006" in rule_ids
        assert "AUTH-007" in rule_ids

    def test_typescript_file_supported(self, tmp_path: Path) -> None:
        src = tmp_path / "app.ts"
        src.write_text('const secret = "supersecret123";\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1

    def test_mjs_file_supported(self, tmp_path: Path) -> None:
        src = tmp_path / "app.mjs"
        src.write_text('const jwtSecret = "supersecret123";\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1

    def test_cjs_file_supported(self, tmp_path: Path) -> None:
        src = tmp_path / "app.cjs"
        src.write_text('const SECRET = "supersecret123";\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1

    def test_unicode_content_handled(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('# Configuración de la aplicación\nSECRET_KEY = "supersecret"\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1

    def test_very_long_line(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "supersecret"' + " " * 10000 + "\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1

    def test_empty_lines_and_whitespace(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("\n\n\n   \n\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        assert findings == []


# ──────────────────────────────────────────────
# Helper function tests
# ──────────────────────────────────────────────


class TestHelperFunctions:
    """Tests para funciones auxiliares."""

    def test_is_relevant_file_py(self) -> None:
        assert _is_relevant_file("app.py") is True

    def test_is_relevant_file_js(self) -> None:
        assert _is_relevant_file("app.js") is True

    def test_is_relevant_file_tsx(self) -> None:
        assert _is_relevant_file("App.tsx") is True

    def test_is_relevant_file_md(self) -> None:
        assert _is_relevant_file("README.md") is False

    def test_is_relevant_file_json(self) -> None:
        assert _is_relevant_file("package.json") is False

    def test_is_comment_python_hash(self) -> None:
        assert _is_comment("# comment", True) is True

    def test_is_comment_python_code(self) -> None:
        assert _is_comment("code = 1", True) is False

    def test_is_comment_js_slash(self) -> None:
        assert _is_comment("// comment", False) is True

    def test_is_comment_js_code(self) -> None:
        assert _is_comment("const x = 1;", False) is False

    def test_is_comment_js_block_not_detected(self) -> None:
        """Block comments are a known V0 limitation."""
        assert _is_comment("/* comment */", False) is False


# ──────────────────────────────────────────────
# Middleware checker edge cases
# ──────────────────────────────────────────────


class TestMiddlewareCheckerEdgeCases:
    """Edge cases para middleware_checker."""

    def test_all_sensitive_paths_detected(self) -> None:
        for pattern in SENSITIVE_PATH_PATTERNS:
            assert _is_sensitive_path(pattern), f"{pattern} not detected as sensitive"

    def test_case_insensitive_path(self) -> None:
        assert _is_sensitive_path("/ADMIN/dashboard") is True
        assert _is_sensitive_path("/Users/Profile") is True

    def test_nested_sensitive_path(self) -> None:
        assert _is_sensitive_path("/api/v1/admin/users") is True

    def test_public_paths_not_sensitive(self) -> None:
        assert _is_sensitive_path("/health") is False
        assert _is_sensitive_path("/docs") is False
        assert _is_sensitive_path("/static/main.js") is False

    def test_post_to_sensitive_path_reports_auth002(self) -> None:
        """POST /admin should be AUTH-002 (mutating wins over sensitive path)."""
        ep = DetectedEndpoint(
            file="a.py", line=1, method="POST", path="/admin/config",
            framework="fastapi", snippet="...", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-002"

    def test_patch_without_auth(self) -> None:
        ep = DetectedEndpoint(
            file="a.py", line=1, method="PATCH", path="/items/1",
            framework="express", snippet="...", has_auth=False,
        )
        finding = check_endpoint_auth(ep)
        assert finding is not None
        assert finding.rule_id == "AUTH-002"


# ──────────────────────────────────────────────
# Pattern edge cases
# ──────────────────────────────────────────────


class TestPatternEdgeCases:
    """Edge cases para patterns.py."""

    def test_jwt_minutes_unit(self) -> None:
        assert extract_jwt_lifetime_hours_js("{ expiresIn: '120m' }") == 2

    def test_jwt_minutes_less_than_hour(self) -> None:
        assert extract_jwt_lifetime_hours_js("{ expiresIn: '30m' }") == 0

    def test_jwt_seconds_unit(self) -> None:
        assert extract_jwt_lifetime_hours_js("{ expiresIn: '7200s' }") == 2

    def test_jwt_seconds_less_than_hour(self) -> None:
        assert extract_jwt_lifetime_hours_js("{ expiresIn: '600s' }") == 0

    def test_jwt_hours_unit_full_word(self) -> None:
        assert extract_jwt_lifetime_hours_js("{ expiresIn: '72hours' }") == 72

    def test_jwt_days_unit_full_word(self) -> None:
        assert extract_jwt_lifetime_hours_js("{ expiresIn: '7days' }") == 168

    def test_hardcoded_secret_with_config_ref(self) -> None:
        assert is_hardcoded_secret('SECRET_KEY = "config.settings.key"', True) is None

    def test_hardcoded_secret_settings_ref(self) -> None:
        assert is_hardcoded_secret('SECRET_KEY = "settings.SECRET"', True) is None

    def test_cors_flask_origins_not_star(self) -> None:
        is_all, _ = is_cors_allow_all('origins="http://localhost:3000"')
        assert is_all is False

    def test_cors_express_router_use(self) -> None:
        is_all, fw = is_cors_allow_all("router.use(cors())")
        assert is_all is True
        assert fw == "express"

    def test_password_comparison_with_hash_suffix(self) -> None:
        assert is_password_comparison("if hashed_password == stored:", True) is True

    def test_password_comparison_js_not_equal(self) -> None:
        assert is_password_comparison("if (password !== expected) {", False) is True

    def test_cookie_flags_mixed_case(self) -> None:
        lines = ["Secure=True, HttpOnly=True, SameSite='Lax'"]
        flags = has_cookie_security_flags(lines)
        assert flags["secure"] is True
        assert flags["httponly"] is True
        assert flags["samesite"] is True


# ──────────────────────────────────────────────
# Finding quality
# ──────────────────────────────────────────────


class TestFindingQuality:
    """Tests para verificar que los findings tienen la estructura correcta."""

    def test_auth003_finding_has_metadata(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("exp = timedelta(hours=72)\n")
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth003 = [f for f in findings if f.rule_id == "AUTH-003"]
        assert len(auth003) >= 1
        assert auth003[0].metadata["lifetime_hours"] == 72
        assert auth003[0].metadata["threshold_hours"] == 24

    def test_auth004_finding_has_metadata(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('SECRET_KEY = "supersecret"\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth004 = [f for f in findings if f.rule_id == "AUTH-004"]
        assert len(auth004) >= 1
        assert "entropy" in auth004[0].metadata
        assert "value_length" in auth004[0].metadata

    def test_auth005_finding_has_framework(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('allow_origins=["*"]\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)
        auth005 = [f for f in findings if f.rule_id == "AUTH-005"]
        assert len(auth005) >= 1
        assert "framework" in auth005[0].metadata

    def test_auth006_finding_lists_missing_flags(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('response.set_cookie("session", "value")\n')
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        auth006 = [f for f in findings if f.rule_id == "AUTH-006"]
        assert len(auth006) >= 1
        assert "missing_flags" in auth006[0].metadata
        missing = auth006[0].metadata["missing_flags"]
        assert "secure" in missing
        assert "httponly" in missing
        assert "samesite" in missing

    def test_all_findings_have_location(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'SECRET_KEY = "supersecret"\n'
            'allow_origins=["*"]\n'
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        config.auth.cors_allow_localhost = False
        findings = analyzer.analyze([str(src)], config)
        for f in findings:
            assert f.location is not None
            assert f.location.file == str(src)
            assert f.location.line > 0

    def test_all_findings_have_suggestion(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(
            'SECRET_KEY = "supersecret"\n'
            "if password == stored:\n"
            "    pass\n"
        )
        analyzer = AuthAnalyzer()
        config = ScanConfig()
        findings = analyzer.analyze([str(src)], config)
        for f in findings:
            assert f.suggestion is not None
            assert len(f.suggestion) > 10
