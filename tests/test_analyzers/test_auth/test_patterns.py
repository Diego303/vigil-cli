"""Tests para auth patterns detection."""

import pytest

from vigil.analyzers.auth.patterns import (
    extract_jwt_lifetime_hours_js,
    extract_jwt_lifetime_hours_python,
    has_cookie_security_flags,
    has_timing_safe_comparison,
    is_cors_allow_all,
    is_hardcoded_secret,
    is_password_comparison,
)


class TestJWTLifetimePython:
    """Tests para extraction de JWT lifetime en Python."""

    def test_timedelta_hours(self) -> None:
        line = "timedelta(hours=72)"
        assert extract_jwt_lifetime_hours_python(line) == 72

    def test_timedelta_days(self) -> None:
        line = "timedelta(days=7)"
        assert extract_jwt_lifetime_hours_python(line) == 168  # 7 * 24

    def test_timedelta_hours_1(self) -> None:
        line = "timedelta(hours=1)"
        assert extract_jwt_lifetime_hours_python(line) == 1

    def test_no_timedelta(self) -> None:
        line = "some_other_function(hours=72)"
        assert extract_jwt_lifetime_hours_python(line) is None

    def test_timedelta_with_spaces(self) -> None:
        line = "timedelta( hours = 48 )"
        assert extract_jwt_lifetime_hours_python(line) == 48

    def test_regular_code_no_match(self) -> None:
        line = 'x = "hello world"'
        assert extract_jwt_lifetime_hours_python(line) is None


class TestJWTLifetimeJS:
    """Tests para extraction de JWT lifetime en JavaScript."""

    def test_expires_in_hours(self) -> None:
        line = "{ expiresIn: '72h' }"
        assert extract_jwt_lifetime_hours_js(line) == 72

    def test_expires_in_days(self) -> None:
        line = "{ expiresIn: '7d' }"
        assert extract_jwt_lifetime_hours_js(line) == 168

    def test_expires_in_hours_double_quotes(self) -> None:
        line = '{ expiresIn: "48h" }'
        assert extract_jwt_lifetime_hours_js(line) == 48

    def test_expires_in_1h(self) -> None:
        line = "{ expiresIn: '1h' }"
        assert extract_jwt_lifetime_hours_js(line) == 1

    def test_no_expires_in(self) -> None:
        line = "const x = 72;"
        assert extract_jwt_lifetime_hours_js(line) is None

    def test_expires_in_seconds_large(self) -> None:
        line = "{ expiresIn: 86400 }"
        assert extract_jwt_lifetime_hours_js(line) == 24

    def test_expires_in_seconds_small(self) -> None:
        line = "{ expiresIn: 3600 }"
        assert extract_jwt_lifetime_hours_js(line) == 1

    def test_expires_in_seconds_less_than_hour(self) -> None:
        line = "{ expiresIn: 1800 }"
        assert extract_jwt_lifetime_hours_js(line) == 0


class TestCORSPatterns:
    """Tests para deteccion de CORS allow all."""

    def test_fastapi_cors_star(self) -> None:
        line = 'allow_origins=["*"]'
        is_all, fw = is_cors_allow_all(line)
        assert is_all is True
        assert fw == "fastapi"

    def test_fastapi_cors_star_single_quotes(self) -> None:
        line = "allow_origins=['*']"
        is_all, fw = is_cors_allow_all(line)
        assert is_all is True
        assert fw == "fastapi"

    def test_flask_cors_star(self) -> None:
        line = 'origins="*"'
        is_all, fw = is_cors_allow_all(line)
        assert is_all is True
        assert fw == "flask"

    def test_express_cors_star(self) -> None:
        line = "origin: '*'"
        is_all, fw = is_cors_allow_all(line)
        assert is_all is True
        assert fw == "express"

    def test_express_cors_default(self) -> None:
        line = "app.use(cors())"
        is_all, fw = is_cors_allow_all(line)
        assert is_all is True
        assert fw == "express"

    def test_specific_origin_no_match(self) -> None:
        line = 'allow_origins=["https://myapp.com"]'
        is_all, _ = is_cors_allow_all(line)
        assert is_all is False

    def test_no_cors(self) -> None:
        line = 'x = "hello"'
        is_all, _ = is_cors_allow_all(line)
        assert is_all is False


class TestHardcodedSecret:
    """Tests para deteccion de secrets hardcodeados."""

    def test_python_secret_key(self) -> None:
        line = 'SECRET_KEY = "supersecret123"'
        result = is_hardcoded_secret(line, is_python=True)
        assert result == "supersecret123"

    def test_python_jwt_secret(self) -> None:
        line = 'JWT_SECRET = "mytoken"'
        result = is_hardcoded_secret(line, is_python=True)
        assert result == "mytoken"

    def test_python_env_reference_no_match(self) -> None:
        line = 'SECRET_KEY = "os.environ[\'KEY\']"'
        result = is_hardcoded_secret(line, is_python=True)
        assert result is None

    def test_js_secret(self) -> None:
        line = "const secret = 'mysecret123';"
        result = is_hardcoded_secret(line, is_python=False)
        assert result == "mysecret123"

    def test_js_env_reference_no_match(self) -> None:
        line = "const secret = 'process.env.SECRET';"
        result = is_hardcoded_secret(line, is_python=False)
        assert result is None

    def test_empty_value_no_match(self) -> None:
        line = 'SECRET_KEY = ""'
        result = is_hardcoded_secret(line, is_python=True)
        assert result is None

    def test_short_value_no_match(self) -> None:
        line = 'SECRET_KEY = "ab"'
        result = is_hardcoded_secret(line, is_python=True)
        assert result is None


class TestCookieFlags:
    """Tests para deteccion de flags de seguridad en cookies."""

    def test_all_flags_present(self) -> None:
        lines = [
            'resp.set_cookie("session", "value",',
            "    secure=True,",
            "    httponly=True,",
            '    samesite="Lax",',
            ")",
        ]
        flags = has_cookie_security_flags(lines)
        assert flags["secure"] is True
        assert flags["httponly"] is True
        assert flags["samesite"] is True

    def test_no_flags(self) -> None:
        lines = ['resp.set_cookie("session", "value")']
        flags = has_cookie_security_flags(lines)
        assert flags["secure"] is False
        assert flags["httponly"] is False
        assert flags["samesite"] is False

    def test_partial_flags(self) -> None:
        lines = [
            'resp.set_cookie("session", "value",',
            "    secure=True)",
        ]
        flags = has_cookie_security_flags(lines)
        assert flags["secure"] is True
        assert flags["httponly"] is False
        assert flags["samesite"] is False

    def test_js_flags(self) -> None:
        lines = [
            "res.cookie('token', value, {",
            "    secure: true,",
            "    httpOnly: true,",
            "    sameSite: 'strict'",
            "});",
        ]
        flags = has_cookie_security_flags(lines)
        assert flags["secure"] is True
        assert flags["httponly"] is True
        assert flags["samesite"] is True


class TestPasswordComparison:
    """Tests para deteccion de comparacion de passwords."""

    def test_python_direct_comparison(self) -> None:
        line = 'if password == stored_password:'
        assert is_password_comparison(line, is_python=True) is True

    def test_python_not_equal(self) -> None:
        line = 'if password != expected:'
        assert is_password_comparison(line, is_python=True) is True

    def test_js_strict_comparison(self) -> None:
        line = 'if (password === storedHash) {'
        assert is_password_comparison(line, is_python=False) is True

    def test_non_password_comparison(self) -> None:
        line = 'if username == "admin":'
        assert is_password_comparison(line, is_python=True) is False

    def test_timing_safe_is_safe(self) -> None:
        line = "hmac.compare_digest(password, stored)"
        assert has_timing_safe_comparison(line) is True

    def test_bcrypt_is_safe(self) -> None:
        line = "bcrypt.compare(password, hash)"
        assert has_timing_safe_comparison(line) is True

    def test_crypto_timing_safe(self) -> None:
        line = "crypto.timingSafeEqual(buf1, buf2)"
        assert has_timing_safe_comparison(line) is True

    def test_no_timing_safe(self) -> None:
        line = 'if password == "abc":'
        assert has_timing_safe_comparison(line) is False
