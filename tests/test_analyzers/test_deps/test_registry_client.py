"""Tests para registry client (PyPI + npm)."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from vigil.analyzers.deps.registry_client import (
    CACHE_DIR,
    PackageInfo,
    RegistryClient,
)


class TestPackageInfo:
    """Tests para PackageInfo dataclass."""

    def test_basic_creation(self) -> None:
        info = PackageInfo(name="flask", exists=True, ecosystem="pypi")
        assert info.name == "flask"
        assert info.exists is True
        assert info.ecosystem == "pypi"
        assert info.error is None

    def test_nonexistent_package(self) -> None:
        info = PackageInfo(name="fake-pkg", exists=False, ecosystem="pypi")
        assert info.exists is False

    def test_created_datetime_valid(self) -> None:
        info = PackageInfo(
            name="test",
            exists=True,
            ecosystem="pypi",
            created_at="2024-01-15T12:00:00+00:00",
        )
        dt = info.created_datetime
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1

    def test_created_datetime_none(self) -> None:
        info = PackageInfo(name="test", exists=True, ecosystem="pypi")
        assert info.created_datetime is None

    def test_age_days(self) -> None:
        info = PackageInfo(
            name="test",
            exists=True,
            ecosystem="pypi",
            created_at="2020-01-01T00:00:00+00:00",
        )
        age = info.age_days
        assert age is not None
        assert age > 1000  # Definitely more than 1000 days old

    def test_age_days_none_when_no_created_at(self) -> None:
        info = PackageInfo(name="test", exists=True, ecosystem="pypi")
        assert info.age_days is None


class TestRegistryClientCache:
    """Tests para el sistema de cache del RegistryClient."""

    def test_cache_write_and_read(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient(cache_ttl_hours=24)

            info = PackageInfo(name="flask", exists=True, ecosystem="pypi")
            client._set_cache("test_key", info)

            cached = client._get_cache("test_key")
            assert cached is not None
            assert cached.name == "flask"
            assert cached.exists is True

            client.close()

    def test_cache_expired(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient(cache_ttl_hours=0)  # 0 hours = always expired

            info = PackageInfo(name="flask", exists=True, ecosystem="pypi")
            client._set_cache("test_key", info)

            # Make cache file old
            cache_file = tmp_path / "test_key.json"
            if cache_file.exists():
                import os

                old_time = time.time() - 100
                os.utime(cache_file, (old_time, old_time))

            cached = client._get_cache("test_key")
            assert cached is None

            client.close()

    def test_cache_miss(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            cached = client._get_cache("nonexistent_key")
            assert cached is None
            client.close()

    def test_cache_corrupt_json(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            (tmp_path / "corrupt_key.json").write_text("not json {{{")
            cached = client._get_cache("corrupt_key")
            assert cached is None
            client.close()

    def test_sanitize_key(self) -> None:
        assert RegistryClient._sanitize_key("pypi_flask") == "pypi_flask"
        assert RegistryClient._sanitize_key("npm_@scope/pkg") == "npm__at_scope__pkg"


class TestRegistryClientPyPI:
    """Tests para verificacion de paquetes en PyPI."""

    def test_check_pypi_404(self, tmp_path: Path) -> None:
        """Paquete que no existe devuelve exists=False."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response),
        ):
            client = RegistryClient()
            result = client.check_pypi("nonexistent-package")

            assert result.exists is False
            assert result.name == "nonexistent-package"
            assert result.ecosystem == "pypi"
            client.close()

    def test_check_pypi_200(self, tmp_path: Path) -> None:
        """Paquete que existe devuelve informacion completa."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {
                "version": "3.0.0",
                "summary": "A web framework",
                "project_urls": {"Source": "https://github.com/pallets/flask"},
            },
            "releases": {
                "2.0.0": [{"upload_time_iso_8601": "2021-05-11T00:00:00Z"}],
                "3.0.0": [{"upload_time_iso_8601": "2023-09-30T00:00:00Z"}],
            },
        }

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response),
        ):
            client = RegistryClient()
            result = client.check_pypi("flask")

            assert result.exists is True
            assert result.name == "flask"
            assert result.latest_version == "3.0.0"
            assert result.source_url == "https://github.com/pallets/flask"
            assert "2.0.0" in result.versions
            assert "3.0.0" in result.versions
            assert result.created_at is not None
            client.close()

    def test_check_pypi_network_error(self, tmp_path: Path) -> None:
        """Error de red asume que el paquete existe para evitar falsos positivos."""
        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(
                httpx.Client, "get", side_effect=httpx.ConnectError("Connection refused")
            ),
        ):
            client = RegistryClient()
            result = client.check_pypi("flask")

            assert result.exists is True  # Assume exists on error
            assert result.error is not None
            assert "Network error" in result.error
            client.close()

    def test_check_pypi_uses_cache(self, tmp_path: Path) -> None:
        """Segunda llamada al mismo paquete usa cache."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {"version": "3.0.0", "summary": "Test"},
            "releases": {},
        }

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response) as mock_get,
        ):
            client = RegistryClient()
            result1 = client.check_pypi("flask")
            result2 = client.check_pypi("flask")

            assert result1.name == result2.name
            # HTTP should only be called once (second call uses cache)
            assert mock_get.call_count == 1
            client.close()


class TestRegistryClientNpm:
    """Tests para verificacion de paquetes en npm."""

    def test_check_npm_404(self, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response),
        ):
            client = RegistryClient()
            result = client.check_npm("nonexistent-package")

            assert result.exists is False
            assert result.ecosystem == "npm"
            client.close()

    def test_check_npm_200(self, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "dist-tags": {"latest": "4.18.2"},
            "time": {"created": "2010-12-29T19:38:25.450Z"},
            "versions": {"4.17.0": {}, "4.18.0": {}, "4.18.2": {}},
            "repository": {"type": "git", "url": "https://github.com/expressjs/express"},
            "description": "Fast web framework",
            "maintainers": [{"name": "dougwilson"}, {"name": "wesleytodd"}],
        }

        with (
            patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path),
            patch.object(httpx.Client, "get", return_value=mock_response),
        ):
            client = RegistryClient()
            result = client.check_npm("express")

            assert result.exists is True
            assert result.latest_version == "4.18.2"
            assert result.source_url == "https://github.com/expressjs/express"
            assert result.maintainers_count == 2
            assert result.created_at is not None
            client.close()


class TestRegistryClientCheck:
    """Tests para el metodo check() generico."""

    def test_check_routes_pypi(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            with patch.object(client, "check_pypi") as mock:
                mock.return_value = PackageInfo(
                    name="flask", exists=True, ecosystem="pypi"
                )
                result = client.check("flask", "pypi")
                mock.assert_called_once_with("flask")
                assert result.ecosystem == "pypi"
            client.close()

    def test_check_routes_npm(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            with patch.object(client, "check_npm") as mock:
                mock.return_value = PackageInfo(
                    name="express", exists=True, ecosystem="npm"
                )
                result = client.check("express", "npm")
                mock.assert_called_once_with("express")
                assert result.ecosystem == "npm"
            client.close()

    def test_check_unknown_ecosystem(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            client = RegistryClient()
            with pytest.raises(ValueError, match="Unknown ecosystem"):
                client.check("something", "cargo")
            client.close()


class TestRegistryClientContextManager:
    """Tests para context manager."""

    def test_context_manager(self, tmp_path: Path) -> None:
        with patch("vigil.analyzers.deps.registry_client.CACHE_DIR", tmp_path):
            with RegistryClient() as client:
                assert client is not None
            # After exiting, client should be closed
            assert client._client is None
