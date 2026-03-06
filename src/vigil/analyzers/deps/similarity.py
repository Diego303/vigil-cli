"""Deteccion de typosquatting por similitud de nombres."""

import json
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Directorio de datos estaticos
DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data"


def levenshtein_distance(s1: str, s2: str) -> int:
    """Distancia de Levenshtein entre dos strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def normalized_similarity(s1: str, s2: str) -> float:
    """Similaridad normalizada entre 0.0 y 1.0."""
    s1_lower = s1.lower()
    s2_lower = s2.lower()

    if s1_lower == s2_lower:
        return 1.0

    dist = levenshtein_distance(s1_lower, s2_lower)
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - (dist / max_len)


def load_popular_packages(ecosystem: str) -> dict[str, int]:
    """Carga el corpus de paquetes populares (nombre -> descargas semanales).

    Busca primero en DATA_DIR, luego como fallback un corpus minimo built-in.
    """
    filename = f"popular_{ecosystem}.json"
    filepath = DATA_DIR / filename

    if filepath.exists():
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("popular_packages_load_error", file=str(filepath), error=str(e))

    # Fallback: corpus minimo built-in con los paquetes mas populares
    if ecosystem == "pypi":
        return _BUILTIN_POPULAR_PYPI
    elif ecosystem == "npm":
        return _BUILTIN_POPULAR_NPM
    return {}


def find_similar_popular(
    name: str,
    ecosystem: str,
    threshold: float = 0.85,
    popular_packages: dict[str, int] | None = None,
) -> list[tuple[str, float]]:
    """Encuentra paquetes populares con nombres similares.

    Returns:
        Lista de (nombre_popular, similaridad) ordenada por similaridad descendente.
    """
    if popular_packages is None:
        popular_packages = load_popular_packages(ecosystem)

    if not popular_packages:
        return []

    matches: list[tuple[str, float]] = []
    name_lower = name.lower()

    # Normalizacion de nombres para comparacion (PyPI normaliza - y _ como equivalentes)
    name_normalized = _normalize_package_name(name_lower, ecosystem)

    for popular_name in popular_packages:
        popular_lower = popular_name.lower()
        popular_normalized = _normalize_package_name(popular_lower, ecosystem)

        # Exact match tras normalizacion — no es typosquatting
        if name_normalized == popular_normalized:
            continue

        sim = normalized_similarity(name_normalized, popular_normalized)
        if sim >= threshold:
            matches.append((popular_name, sim))

    return sorted(matches, key=lambda x: x[1], reverse=True)


def _normalize_package_name(name: str, ecosystem: str) -> str:
    """Normaliza nombre de paquete para comparacion.

    PyPI trata guiones y underscores como equivalentes.
    npm es case-sensitive pero trata @scope/name aparte.
    """
    if ecosystem == "pypi":
        return name.lower().replace("-", "_").replace(".", "_")
    return name.lower()


# ──────────────────────────────────────────────────────────────────
# Corpus built-in minimo (top ~200 paquetes mas comunes)
# Se usa como fallback cuando no hay data/popular_*.json
# ──────────────────────────────────────────────────────────────────

_BUILTIN_POPULAR_PYPI: dict[str, int] = {
    "requests": 300_000_000,
    "boto3": 250_000_000,
    "urllib3": 240_000_000,
    "setuptools": 220_000_000,
    "certifi": 200_000_000,
    "charset-normalizer": 190_000_000,
    "idna": 185_000_000,
    "typing-extensions": 180_000_000,
    "python-dateutil": 170_000_000,
    "packaging": 160_000_000,
    "pyyaml": 155_000_000,
    "six": 150_000_000,
    "numpy": 145_000_000,
    "botocore": 140_000_000,
    "pip": 135_000_000,
    "s3transfer": 130_000_000,
    "cryptography": 125_000_000,
    "jmespath": 120_000_000,
    "cffi": 115_000_000,
    "pycparser": 110_000_000,
    "pyasn1": 105_000_000,
    "attrs": 100_000_000,
    "platformdirs": 95_000_000,
    "click": 90_000_000,
    "pillow": 85_000_000,
    "pandas": 80_000_000,
    "markupsafe": 78_000_000,
    "jinja2": 76_000_000,
    "wheel": 74_000_000,
    "pygments": 72_000_000,
    "pytz": 70_000_000,
    "filelock": 68_000_000,
    "wrapt": 66_000_000,
    "pydantic": 64_000_000,
    "scipy": 62_000_000,
    "tqdm": 60_000_000,
    "decorator": 58_000_000,
    "protobuf": 56_000_000,
    "grpcio": 54_000_000,
    "jsonschema": 52_000_000,
    "tomli": 50_000_000,
    "google-api-core": 48_000_000,
    "google-auth": 46_000_000,
    "aiohttp": 44_000_000,
    "multidict": 42_000_000,
    "yarl": 40_000_000,
    "frozenlist": 38_000_000,
    "aiosignal": 36_000_000,
    "async-timeout": 34_000_000,
    "werkzeug": 32_000_000,
    "flask": 30_000_000,
    "sqlalchemy": 28_000_000,
    "psycopg2": 26_000_000,
    "pytest": 24_000_000,
    "httpx": 22_000_000,
    "httpcore": 20_000_000,
    "anyio": 18_000_000,
    "sniffio": 16_000_000,
    "fastapi": 14_000_000,
    "uvicorn": 12_000_000,
    "starlette": 10_000_000,
    "django": 8_000_000,
    "celery": 6_000_000,
    "redis": 5_500_000,
    "pymongo": 5_000_000,
    "matplotlib": 4_500_000,
    "scikit-learn": 4_000_000,
    "tensorflow": 3_500_000,
    "torch": 3_000_000,
    "transformers": 2_500_000,
    "beautifulsoup4": 2_000_000,
    "lxml": 1_800_000,
    "paramiko": 1_600_000,
    "pyjwt": 1_400_000,
    "python-dotenv": 1_200_000,
    "gunicorn": 1_000_000,
    "black": 900_000,
    "ruff": 850_000,
    "mypy": 800_000,
    "flake8": 750_000,
    "isort": 700_000,
    "structlog": 650_000,
    "alembic": 600_000,
    "marshmallow": 550_000,
    "rich": 500_000,
    "typer": 450_000,
    "pendulum": 400_000,
    "arrow": 350_000,
    "docutils": 300_000,
    "sphinx": 250_000,
    "coverage": 200_000,
    "hypothesis": 150_000,
    "faker": 140_000,
    "networkx": 130_000,
    "sympy": 120_000,
    "seaborn": 110_000,
    "plotly": 100_000,
    "bokeh": 95_000,
    "openpyxl": 90_000,
    "xlsxwriter": 85_000,
    "pydantic-core": 80_000,
    "annotated-types": 75_000,
    "orjson": 70_000,
    "ujson": 65_000,
    "msgpack": 60_000,
    "psutil": 55_000,
    "watchdog": 50_000,
    "colorama": 45_000,
}

_BUILTIN_POPULAR_NPM: dict[str, int] = {
    "lodash": 50_000_000,
    "react": 25_000_000,
    "chalk": 22_000_000,
    "express": 20_000_000,
    "tslib": 18_000_000,
    "axios": 16_000_000,
    "commander": 14_000_000,
    "moment": 12_000_000,
    "debug": 11_000_000,
    "uuid": 10_000_000,
    "glob": 9_000_000,
    "fs-extra": 8_500_000,
    "semver": 8_000_000,
    "minimist": 7_500_000,
    "yargs": 7_000_000,
    "inquirer": 6_500_000,
    "dotenv": 6_000_000,
    "jsonwebtoken": 5_500_000,
    "cors": 5_000_000,
    "body-parser": 4_500_000,
    "webpack": 4_000_000,
    "typescript": 3_800_000,
    "eslint": 3_600_000,
    "prettier": 3_400_000,
    "jest": 3_200_000,
    "mocha": 3_000_000,
    "next": 2_800_000,
    "vue": 2_600_000,
    "angular": 2_400_000,
    "rxjs": 2_200_000,
    "mongoose": 2_000_000,
    "mysql2": 1_800_000,
    "pg": 1_600_000,
    "redis": 1_400_000,
    "socket.io": 1_200_000,
    "passport": 1_000_000,
    "bcrypt": 900_000,
    "bcryptjs": 850_000,
    "helmet": 800_000,
    "morgan": 750_000,
    "cookie-parser": 700_000,
    "multer": 650_000,
    "nodemon": 600_000,
    "concurrently": 550_000,
    "cross-env": 500_000,
    "rimraf": 450_000,
    "mkdirp": 400_000,
    "ora": 350_000,
    "zod": 280_000,
    "prisma": 260_000,
    "drizzle-orm": 240_000,
    "tailwindcss": 220_000,
    "postcss": 200_000,
    "autoprefixer": 180_000,
    "vite": 160_000,
    "esbuild": 140_000,
    "rollup": 120_000,
    "vitest": 100_000,
    "cypress": 90_000,
    "playwright": 80_000,
    "supertest": 70_000,
    "nock": 60_000,
    "sinon": 55_000,
    "chai": 50_000,
    "http-errors": 45_000,
    "compression": 40_000,
    "serve-static": 35_000,
    "path-to-regexp": 30_000,
}
