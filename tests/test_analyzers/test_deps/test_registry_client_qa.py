"""QA tests adicionales para RegistryClient.

Cubre: edge cases de cache, respuestas HTTP inesperadas, formatos de
fecha, npm scoped packages, serialización, timeouts, y context manager.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from vigil.analyzers.deps.registry_client import (
    CACHE_DIR,
    PackageInfo,
    RegistryClient,
)


# ──────────────────────────────────────────────────────────────────
# PackageInfo — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestPackageInfoEdgeCases:
    """Edge cases para PackageInfo."""

    def test_created_datetime_invalid_format(self) -> None:
        """Invalid created_at string returns None."""
        info = PackageInfo(
            name="test",
            exists=True,
            ecosystem="pypi",
            created_at="not-a-date",
        )

        assert info.created_datetime is None

    def test_created_datetime_empty_string(self) -> None:
        """Empty string created_at returns None."""
        info = PackageInfo(
            name="test",
            exists=True,
            ecosystem="pypi",
            created_at="",
        )

        assert info.created_datetime is None

    def test_age_days_with_naive_datetime(self) -> None:
        """created_at without timezone info gets UTC assumed."""
        info = PackageInfo(
            name="test",
            exists=True,
            ecosystem="pypi",
            created_at="2020-01-01T00:00:00",
        )

        age = info.age_days
        assert age is not None
        assert age > 1000

    def test_age_days_boundary_today(self) -> None:
        """Package created today has age_days = 0."""
        now = datetime.now(timezone.utc).isoformat()
        info = PackageInfo(
            name="test", exists=True, ecosystem="pypi", created_at=now,
        )

        assert info.age_days == 0

    def test_age_days_exactly_threshold(self) -> None:
        """Package created exactly min_age_days ago."""
        created = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        info = PackageInfo(
            name="test", exists=True, ecosystem="pypi", created_at=created,
        )

        # age_days should be 30 (or close to it depending on time of day)
        assert info.age_days is not None
        assert info.age_days >= 29  # Allow for time-of-day variance

    def test_all_optional_fields_none(self) -> None:
        """PackageInfo with only required fields."""
        info = PackageInfo(name="test", exists=True, ecosystem="pypi")

        assert info.created_at is None
        assert info.weekly_downloads is None
        assert info.source_url is None
        assert info.latest_version is None
        assert info.versions is None
        assert info.maintainers_count is None
        assert info.description is None
        assert info.error is None
        assert info.created_datetime is None
        assert info.age_days is None

    def test_with_error_field(self) -> None:
        """PackageInfo with error field set."""
        info = PackageInfo(
            name="test",
            exists=True,
            ecosystem="pypi",
            error="HTTP 500",
        )

        assert info.error == "HTTP 500"
        assert info.exists is True  # Error assumes exists


# ──────────────────────────────────────────────────────────────────
# RegistryClient — Cache edge cases
# ──────────────────────────────────────────────────────────────────


class TestRegistryClientCacheEdgeCases:
    """Edge cases para el sistema de cache."""

    def test_cache_with_extra_fields_in_json(self, tmp_path: Path) -> None:
        """Cache file with extra unknown fields is handled gracefully."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            cache_data = {
                "name": "flask",
                "exists": True,
                "ecosystem": "pypi",
                "unknown_field": "should cause error",
            }
            (tmp_path / "test_key.json").write_text(json.dumps(cache_data))

            # Should return None (TypeError caught from unexpected kwargs)
            cached = client._get_cache("test_key")
            assert cached is None
            client.close()

    def test_cache_with_missing_required_fields(self, tmp_path: Path) -> None:
        """Cache file missing required fields returns None."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            (tmp_path / "incomplete.json").write_text('{"name": "flask"}')

            cached = client._get_cache("incomplete")
            assert cached is None
            client.close()

    def test_cache_zero_ttl(self, tmp_path: Path) -> None:
        """TTL of 0 hours means cache always expired."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient(cache_ttl_hours=0)

            info = PackageInfo(name="test", exists=True, ecosystem="pypi")
            client._set_cache("zero_ttl", info)

            # Should be immediately expired (0 seconds TTL)
            cached = client._get_cache("zero_ttl")
            assert cached is None
            client.close()

    def test_cache_very_large_ttl(self, tmp_path: Path) -> None:
        """Very large TTL keeps cache valid."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient(cache_ttl_hours=999999)

            info = PackageInfo(name="test", exists=True, ecosystem="pypi")
            client._set_cache("large_ttl", info)

            cached = client._get_cache("large_ttl")
            assert cached is not None
            assert cached.name == "test"
            client.close()

    def test_cache_preserves_all_fields(self, tmp_path: Path) -> None:
        """Cache round-trip preserves all PackageInfo fields."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()

            info = PackageInfo(
                name="flask",
                exists=True,
                ecosystem="pypi",
                created_at="2010-04-06T00:00:00+00:00",
                weekly_downloads=30000000,
                source_url="https://github.com/pallets/flask",
                latest_version="3.0.0",
                versions=["2.0.0", "3.0.0"],
                maintainers_count=5,
                description="A web framework",
            )
            client._set_cache("full_fields", info)

            cached = client._get_cache("full_fields")
            assert cached is not None
            assert cached.name == "flask"
            assert cached.exists is True
            assert cached.created_at == "2010-04-06T00:00:00+00:00"
            assert cached.source_url == "https://github.com/pallets/flask"
            assert cached.latest_version == "3.0.0"
            assert cached.versions == ["2.0.0", "3.0.0"]
            assert cached.description == "A web framework"
            client.close()

    def test_cache_readonly_dir(self, tmp_path: Path) -> None:
        """Write to read-only cache dir fails silently."""
        readonly = tmp_path / "readonly"
        readonly.mkdir()

        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", readonly):
            client = RegistryClient()
            info = PackageInfo(name="test", exists=True, ecosystem="pypi")

            # Make dir read-only
            readonly.chmod(0o444)
            try:
                # Should not raise
                client._set_cache("test", info)
            finally:
                readonly.chmod(0o755)

            client.close()


# ──────────────────────────────────────────────────────────────────
# RegistryClient — Sanitize key
# ──────────────────────────────────────────────────────────────────


class TestSanitizeKey:
    """Tests para _sanitize_key."""

    def test_scoped_npm_package(self) -> None:
        assert RegistryClient._sanitize_key("npm_@scope/name") == "npm__at_scope__name"

    def test_path_traversal_attempt(self) -> None:
        """Path traversal characters are sanitized."""
        result = RegistryClient._sanitize_key("npm_../../etc/passwd")
        assert "/" not in result
        assert ".." in result  # dots are preserved but slashes removed

    def test_colon_in_key(self) -> None:
        assert RegistryClient._sanitize_key("pypi:flask") == "pypi_flask"

    def test_plain_key(self) -> None:
        assert RegistryClient._sanitize_key("pypi_flask") == "pypi_flask"


# ──────────────────────────────────────────────────────────────────
# RegistryClient — PyPI response parsing
# ──────────────────────────────────────────────────────────────────


class TestPyPIResponseParsing:
    """Tests para _parse_pypi_response."""

    def test_source_url_repository_key(self, tmp_path: Path) -> None:
        """Finds source_url from 'Repository' key."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "info": {
                    "version": "1.0",
                    "project_urls": {"Repository": "https://github.com/test/test"},
                },
                "releases": {},
            }

            result = client._parse_pypi_response("test", data)

            assert result.source_url == "https://github.com/test/test"
            client.close()

    def test_source_url_homepage_fallback(self, tmp_path: Path) -> None:
        """Falls back to home_page when no project_urls match."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "info": {
                    "version": "1.0",
                    "project_urls": {"Documentation": "https://docs.example.com"},
                    "home_page": "https://example.com",
                },
                "releases": {},
            }

            result = client._parse_pypi_response("test", data)

            assert result.source_url == "https://example.com"
            client.close()

    def test_source_url_none_when_no_urls(self, tmp_path: Path) -> None:
        """No source_url when no project_urls or home_page."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "info": {"version": "1.0", "project_urls": None},
                "releases": {},
            }

            result = client._parse_pypi_response("test", data)

            assert result.source_url is None
            client.close()

    def test_created_at_from_earliest_upload(self, tmp_path: Path) -> None:
        """created_at uses the earliest upload time across all releases."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "info": {"version": "2.0"},
                "releases": {
                    "2.0": [{"upload_time_iso_8601": "2024-01-15T12:00:00Z"}],
                    "1.0": [{"upload_time_iso_8601": "2023-06-01T00:00:00Z"}],
                },
            }

            result = client._parse_pypi_response("test", data)

            assert result.created_at is not None
            # Should be the 2023 date (earliest)
            assert "2023" in result.created_at
            client.close()

    def test_empty_releases(self, tmp_path: Path) -> None:
        """Package with empty releases dict."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {"info": {"version": "1.0"}, "releases": {}}

            result = client._parse_pypi_response("test", data)

            assert result.exists is True
            assert result.created_at is None
            assert result.versions is None
            client.close()

    def test_unknown_http_status(self, tmp_path: Path) -> None:
        """Unknown HTTP status assumes package exists."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response),
        ):
            client = RegistryClient()
            result = client.check_pypi("test-pkg")

            assert result.exists is True
            assert result.error == "HTTP 500"
            client.close()


# ──────────────────────────────────────────────────────────────────
# RegistryClient — npm response parsing
# ──────────────────────────────────────────────────────────────────


class TestNpmResponseParsing:
    """Tests para _parse_npm_response."""

    def test_repository_as_string(self, tmp_path: Path) -> None:
        """npm repository field can be a plain string."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "dist-tags": {"latest": "1.0.0"},
                "time": {},
                "versions": {"1.0.0": {}},
                "repository": "https://github.com/test/test",
            }

            result = client._parse_npm_response("test", data)

            assert result.source_url == "https://github.com/test/test"
            client.close()

    def test_repository_as_dict(self, tmp_path: Path) -> None:
        """npm repository as {type, url} dict."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "dist-tags": {"latest": "1.0.0"},
                "time": {},
                "versions": {"1.0.0": {}},
                "repository": {"type": "git", "url": "git+https://github.com/test/test"},
            }

            result = client._parse_npm_response("test", data)

            assert result.source_url == "git+https://github.com/test/test"
            client.close()

    def test_no_repository(self, tmp_path: Path) -> None:
        """npm package without repository."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "dist-tags": {"latest": "1.0.0"},
                "time": {},
                "versions": {"1.0.0": {}},
            }

            result = client._parse_npm_response("test", data)

            assert result.source_url is None
            client.close()

    def test_empty_versions_dict(self, tmp_path: Path) -> None:
        """npm package with empty versions returns None."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            data = {
                "dist-tags": {"latest": "1.0.0"},
                "time": {},
                "versions": {},
            }

            result = client._parse_npm_response("test", data)

            assert result.versions is None
            client.close()

    def test_npm_scoped_package_cache(self, tmp_path: Path) -> None:
        """Scoped npm packages have correct cache key."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response),
        ):
            client = RegistryClient()
            result = client.check_npm("@scope/package")

            assert result.exists is False
            # Cache file should exist with sanitized name
            cache_files = list(tmp_path.glob("*.json"))
            assert len(cache_files) == 1
            assert "__" in cache_files[0].name
            client.close()


# ──────────────────────────────────────────────────────────────────
# RegistryClient — Context manager and close
# ──────────────────────────────────────────────────────────────────


class TestRegistryClientLifecycle:
    """Tests para lifecycle del RegistryClient."""

    def test_close_without_init(self, tmp_path: Path) -> None:
        """Closing client that was never used doesn't crash."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            client.close()
            assert client._client is None

    def test_double_close(self, tmp_path: Path) -> None:
        """Closing twice doesn't crash."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            client.close()
            client.close()  # Should not raise
            assert client._client is None

    def test_lazy_client_init(self, tmp_path: Path) -> None:
        """HTTP client is not created until first request."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            assert client._client is None

            # Trigger lazy init
            http_client = client._get_client()
            assert http_client is not None
            assert client._client is not None

            client.close()

    def test_context_manager_closes_client(self, tmp_path: Path) -> None:
        """Context manager properly closes the HTTP client."""
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            with RegistryClient() as client:
                _ = client._get_client()
                assert client._client is not None

            assert client._client is None
