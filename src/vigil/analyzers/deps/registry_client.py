"""Cliente HTTP para verificar paquetes en PyPI y npm."""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import time

import httpx
import structlog

logger = structlog.get_logger()

CACHE_DIR = Path.home() / ".cache" / "vigil" / "registry"


@dataclass
class PackageInfo:
    """Informacion de un paquete del registry."""

    name: str
    exists: bool
    ecosystem: str  # "pypi" | "npm"
    created_at: str | None = None  # ISO format string para serializacion
    weekly_downloads: int | None = None
    source_url: str | None = None
    latest_version: str | None = None
    versions: list[str] | None = None
    maintainers_count: int | None = None
    description: str | None = None
    error: str | None = None

    @property
    def created_datetime(self) -> datetime | None:
        """Convierte created_at string a datetime."""
        if self.created_at:
            try:
                return datetime.fromisoformat(self.created_at)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def age_days(self) -> int | None:
        """Dias desde la creacion del paquete."""
        dt = self.created_datetime
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        return None


class RegistryClient:
    """Verifica paquetes contra PyPI y npm con cache local."""

    def __init__(self, cache_ttl_hours: int = 24, timeout: int = 10) -> None:
        self.cache_ttl = cache_ttl_hours * 3600
        self.timeout = timeout
        self._client: httpx.Client | None = None
        self._ensure_cache_dir()

    def _get_client(self) -> httpx.Client:
        """Lazy init del cliente HTTP para reutilizar conexiones."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
        return self._client

    def check_pypi(self, package_name: str) -> PackageInfo:
        """Verifica un paquete en PyPI."""
        cached = self._get_cache(f"pypi_{package_name}")
        if cached:
            return cached

        try:
            client = self._get_client()
            resp = client.get(f"https://pypi.org/pypi/{package_name}/json")

            if resp.status_code == 404:
                result = PackageInfo(
                    name=package_name, exists=False, ecosystem="pypi"
                )
            elif resp.status_code == 200:
                result = self._parse_pypi_response(package_name, resp.json())
            else:
                # Estado desconocido — asumir que existe para evitar falsos positivos
                result = PackageInfo(
                    name=package_name,
                    exists=True,
                    ecosystem="pypi",
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.HTTPError as e:
            logger.warning("pypi_request_error", package=package_name, error=str(e))
            result = PackageInfo(
                name=package_name,
                exists=True,
                ecosystem="pypi",
                error=f"Network error: {e}",
            )

        self._set_cache(f"pypi_{package_name}", result)
        return result

    def check_npm(self, package_name: str) -> PackageInfo:
        """Verifica un paquete en npm."""
        # npm soporta scoped packages como @scope/name
        cache_key = f"npm_{package_name.replace('/', '__')}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            client = self._get_client()
            # Para npm, usar abbreviated metadata para requests mas rapidos
            resp = client.get(
                f"https://registry.npmjs.org/{package_name}",
                headers={"Accept": "application/json"},
            )

            if resp.status_code == 404:
                result = PackageInfo(
                    name=package_name, exists=False, ecosystem="npm"
                )
            elif resp.status_code == 200:
                result = self._parse_npm_response(package_name, resp.json())
            else:
                result = PackageInfo(
                    name=package_name,
                    exists=True,
                    ecosystem="npm",
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.HTTPError as e:
            logger.warning("npm_request_error", package=package_name, error=str(e))
            result = PackageInfo(
                name=package_name,
                exists=True,
                ecosystem="npm",
                error=f"Network error: {e}",
            )

        self._set_cache(cache_key, result)
        return result

    def check(self, package_name: str, ecosystem: str) -> PackageInfo:
        """Verifica un paquete en el ecosystem correcto."""
        if ecosystem == "pypi":
            return self.check_pypi(package_name)
        elif ecosystem == "npm":
            return self.check_npm(package_name)
        raise ValueError(f"Unknown ecosystem: {ecosystem}")

    def close(self) -> None:
        """Cierra el cliente HTTP."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "RegistryClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _parse_pypi_response(self, name: str, data: dict) -> PackageInfo:
        """Parsea la respuesta de PyPI JSON API."""
        info = data.get("info", {})
        releases = data.get("releases", {})

        # Fecha de creacion = upload_time de la primera release
        created_at = None
        if releases:
            all_upload_times: list[str] = []
            for version_files in releases.values():
                for file_info in version_files:
                    upload_time = file_info.get("upload_time_iso_8601")
                    if upload_time:
                        all_upload_times.append(upload_time)
            if all_upload_times:
                earliest = min(all_upload_times)
                try:
                    dt = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
                    created_at = dt.isoformat()
                except ValueError:
                    pass

        # Source URL
        source_url = None
        project_urls = info.get("project_urls") or {}
        for key in ("Source", "Repository", "Homepage", "Source Code", "Code"):
            if key in project_urls:
                source_url = project_urls[key]
                break
        if not source_url:
            source_url = info.get("home_page")

        return PackageInfo(
            name=name,
            exists=True,
            ecosystem="pypi",
            created_at=created_at,
            source_url=source_url,
            latest_version=info.get("version"),
            versions=list(releases.keys()) if releases else None,
            description=info.get("summary"),
        )

    def _parse_npm_response(self, name: str, data: dict) -> PackageInfo:
        """Parsea la respuesta de npm registry."""
        time_data = data.get("time", {})
        created_str = time_data.get("created")
        created_at = None
        if created_str:
            try:
                dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                created_at = dt.isoformat()
            except ValueError:
                pass

        # Source URL
        repo = data.get("repository")
        source_url = None
        if isinstance(repo, dict):
            source_url = repo.get("url")
        elif isinstance(repo, str):
            source_url = repo

        return PackageInfo(
            name=name,
            exists=True,
            ecosystem="npm",
            created_at=created_at,
            latest_version=data.get("dist-tags", {}).get("latest"),
            versions=list(data.get("versions", {}).keys()) or None,
            source_url=source_url,
            description=data.get("description"),
            maintainers_count=len(data.get("maintainers", [])),
        )

    def _ensure_cache_dir(self) -> None:
        """Crea el directorio de cache si no existe."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.debug("cache_dir_create_failed")

    def _get_cache(self, key: str) -> PackageInfo | None:
        """Lee del cache local."""
        cache_file = CACHE_DIR / f"{self._sanitize_key(key)}.json"
        if not cache_file.exists():
            return None
        try:
            age = time.time() - cache_file.stat().st_mtime
            if age >= self.cache_ttl:
                return None
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return PackageInfo(**data)
        except (json.JSONDecodeError, TypeError, OSError):
            return None

    def _set_cache(self, key: str, info: PackageInfo) -> None:
        """Escribe al cache local."""
        cache_file = CACHE_DIR / f"{self._sanitize_key(key)}.json"
        try:
            serializable = asdict(info)
            cache_file.write_text(
                json.dumps(serializable, default=str), encoding="utf-8"
            )
        except OSError:
            logger.debug("cache_write_failed", key=key)

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Sanitiza una key para usarla como nombre de archivo."""
        return key.replace("/", "__").replace("@", "_at_").replace(":", "_")
