#!/usr/bin/env python3
"""Genera data/popular_pypi.json y data/popular_npm.json.

Descarga los top 5000 paquetes mas populares de PyPI y npm,
almacenandolos como JSON dict de {nombre: descargas_semanales}.

Uso:
    python scripts/fetch_popular_packages.py
    python scripts/fetch_popular_packages.py --pypi-only
    python scripts/fetch_popular_packages.py --npm-only
    python scripts/fetch_popular_packages.py --top 1000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# Directorio de salida
DATA_DIR = Path(__file__).parent.parent / "data"

# Fuentes de datos
PYPI_TOP_URL = (
    "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
)
NPM_REGISTRY_URL = "https://registry.npmjs.org"
NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"

# Top npm packages — lista curada de los paquetes npm mas descargados.
# npm no tiene una API publica de "top packages por descargas", por lo que
# usamos la API de search con popularity sorting y complementamos con una
# lista base de paquetes conocidos como los mas populares del ecosistema.
_NPM_SEED_PACKAGES: list[str] = [
    # Core utilities
    "lodash", "underscore", "ramda", "rxjs", "tslib", "uuid",
    "semver", "debug", "ms", "minimist", "yargs", "commander",
    "chalk", "colors", "ora", "inquirer", "prompts", "glob",
    "minimatch", "micromatch", "picomatch", "fast-glob",
    "fs-extra", "mkdirp", "rimraf", "del", "cpy",
    "path-to-regexp", "resolve", "which", "cross-spawn",
    "execa", "shelljs", "npm-run-all", "concurrently",
    # Web frameworks
    "express", "koa", "fastify", "hapi", "nest", "next",
    "nuxt", "gatsby", "remix", "astro",
    # React ecosystem
    "react", "react-dom", "react-router", "react-router-dom",
    "react-redux", "redux", "redux-thunk", "redux-saga",
    "zustand", "jotai", "recoil", "mobx", "mobx-react",
    "styled-components", "emotion", "@emotion/react", "@emotion/styled",
    "classnames", "clsx",
    # Vue ecosystem
    "vue", "vuex", "pinia", "vue-router",
    # Angular
    "@angular/core", "@angular/common", "@angular/forms",
    "@angular/router", "@angular/compiler",
    # HTTP & networking
    "axios", "node-fetch", "got", "superagent", "request",
    "undici", "ky", "isomorphic-fetch", "cross-fetch",
    # Testing
    "jest", "mocha", "chai", "sinon", "nock", "supertest",
    "vitest", "cypress", "playwright", "@playwright/test",
    "puppeteer", "testing-library", "@testing-library/react",
    "@testing-library/jest-dom", "nyc", "c8", "istanbul",
    # Build tools
    "webpack", "rollup", "esbuild", "vite", "parcel",
    "babel", "@babel/core", "@babel/preset-env", "@babel/preset-react",
    "terser", "uglify-js", "cssnano", "postcss", "autoprefixer",
    "sass", "less", "stylus",
    # TypeScript
    "typescript", "ts-node", "tsx", "tsup",
    # Linting & formatting
    "eslint", "prettier", "stylelint", "tslint",
    "@typescript-eslint/parser", "@typescript-eslint/eslint-plugin",
    # Database
    "mongoose", "sequelize", "typeorm", "prisma", "@prisma/client",
    "drizzle-orm", "knex", "pg", "mysql2", "redis", "ioredis",
    "mongodb", "sqlite3", "better-sqlite3",
    # Auth & security
    "jsonwebtoken", "bcrypt", "bcryptjs", "passport",
    "passport-local", "passport-jwt", "helmet", "cors",
    "csurf", "express-rate-limit", "jose",
    # Middleware
    "body-parser", "cookie-parser", "multer", "morgan",
    "compression", "serve-static", "serve-favicon",
    "express-session", "connect-redis",
    # Validation
    "zod", "joi", "yup", "ajv", "validator", "class-validator",
    # Date/time
    "moment", "dayjs", "date-fns", "luxon",
    # Logging
    "winston", "pino", "bunyan", "log4js", "loglevel",
    # Config
    "dotenv", "config", "convict", "cosmiconfig",
    # File handling
    "formidable", "busboy", "sharp", "jimp",
    "csv-parser", "csv-stringify", "xlsx", "pdf-lib",
    # Templating
    "ejs", "pug", "handlebars", "mustache", "nunjucks",
    # WebSocket
    "socket.io", "ws", "socket.io-client",
    # Process management
    "pm2", "nodemon", "ts-node-dev", "forever",
    # CLI frameworks
    "meow", "oclif", "caporal",
    # Misc popular
    "lodash.merge", "lodash.get", "lodash.set",
    "lodash.clonedeep", "lodash.debounce", "lodash.throttle",
    "async", "bluebird", "p-limit", "p-map", "p-queue",
    "retry", "p-retry", "bottleneck",
    "string-width", "strip-ansi", "wrap-ansi", "ansi-regex",
    "escape-string-regexp", "camelcase", "decamelize",
    "type-fest", "ts-essentials",
    "nanoid", "cuid", "ulid", "short-uuid",
    "cheerio", "jsdom", "puppeteer-core",
    "nodemailer", "twilio", "aws-sdk", "@aws-sdk/client-s3",
    "firebase", "firebase-admin", "supabase",
    "graphql", "apollo-server", "@apollo/client",
    "swagger-ui-express", "swagger-jsdoc",
    "http-errors", "http-status-codes", "statuses",
    "content-type", "mime-types", "mime",
    "qs", "query-string", "url-parse",
    "form-data", "formdata-node",
    "tar", "archiver", "adm-zip", "yauzl",
    "chokidar", "watchpack",
    "lru-cache", "node-cache", "keyv",
    "eventemitter3", "mitt", "tiny-emitter",
    "immer", "immutable",
    "marked", "markdown-it", "remark", "rehype",
    "highlight.js", "prismjs", "shiki",
    "i18next", "intl-messageformat",
    "tailwindcss", "@tailwindcss/forms", "@tailwindcss/typography",
    "daisyui", "headlessui", "@headlessui/react",
    "radix-ui", "@radix-ui/react-dialog",
    "framer-motion", "react-spring", "gsap",
    "three", "d3", "chart.js", "recharts", "nivo",
    "storybook", "@storybook/react",
    "husky", "lint-staged", "commitlint",
    "@commitlint/cli", "@commitlint/config-conventional",
    "release-it", "semantic-release", "changesets",
    "cross-env", "env-cmd", "dotenv-cli",
]


def fetch_pypi_top(count: int = 5000, timeout: int = 30) -> dict[str, int]:
    """Descarga top packages de PyPI.

    Usa https://hugovk.github.io/top-pypi-packages/ (JSON actualizado mensualmente).
    """
    print(f"Fetching top {count} PyPI packages...")

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(PYPI_TOP_URL)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        print(f"Error fetching PyPI data: {e}", file=sys.stderr)
        return {}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error parsing PyPI response: {e}", file=sys.stderr)
        return {}

    rows = data.get("rows", [])

    packages: dict[str, int] = {}
    for row in rows[:count]:
        name = row.get("project", "")
        downloads = row.get("download_count", 0)
        if name:
            packages[name] = downloads

    print(f"  Got {len(packages)} PyPI packages")
    return packages


def fetch_npm_top(count: int = 5000, timeout: int = 30) -> dict[str, int]:
    """Descarga top packages de npm.

    npm no tiene una API directa de "top packages por descargas",
    asi que usamos la API de search con popularity sorting y
    complementamos con una lista seed de paquetes conocidos.

    Estrategia:
    1. Usa la seed list de paquetes conocidos como mas populares
    2. Complementa con busquedas de la API de npm search por popularity
    3. Obtiene download counts reales via la API de npm downloads
    """
    print(f"Fetching top {count} npm packages...")

    packages: dict[str, int] = {}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        # Fase 1: Buscar por popularity en la API de npm
        # La API de search devuelve max 250 resultados por query
        search_terms = [
            "",  # busqueda vacia ordena por popularidad
            "react", "vue", "angular", "express", "node",
            "webpack", "babel", "eslint", "typescript", "jest",
            "database", "server", "client", "auth", "util",
            "cli", "test", "build", "css", "html",
            "api", "http", "json", "xml", "yaml",
            "file", "string", "array", "object", "function",
            "async", "promise", "stream", "event", "error",
            "log", "debug", "config", "env", "path",
            "crypto", "hash", "encode", "decode", "parse",
            "validate", "schema", "format", "transform", "convert",
            "date", "time", "color", "image", "video",
            "email", "sms", "push", "notification", "message",
            "cache", "queue", "worker", "job", "task",
            "orm", "sql", "mongo", "redis", "graphql",
            "rest", "grpc", "websocket", "socket", "rpc",
            "aws", "azure", "gcp", "docker", "kubernetes",
            "deploy", "ci", "cd", "devops", "monitor",
        ]

        for term in search_terms:
            if len(packages) >= count:
                break

            try:
                params = {
                    "text": term,
                    "size": 250,
                    "quality": 0.0,
                    "popularity": 1.0,
                    "maintenance": 0.0,
                }
                resp = client.get(NPM_SEARCH_URL, params=params)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for obj in data.get("objects", []):
                    pkg = obj.get("package", {})
                    name = pkg.get("name", "")
                    # npm search no da downloads directas, usa el score
                    # como proxy temporal; lo reemplazaremos con downloads reales
                    if name and name not in packages:
                        score = obj.get("score", {})
                        detail = score.get("detail", {})
                        popularity = detail.get("popularity", 0)
                        # Normalizar popularity score (0-1) a un valor estimado
                        packages[name] = int(popularity * 50_000_000)

            except (httpx.HTTPError, json.JSONDecodeError, ValueError):
                continue

            # Rate limiting - ser amable con el registry
            time.sleep(0.2)

        # Fase 2: Agregar seed packages que no esten ya
        for name in _NPM_SEED_PACKAGES:
            if name not in packages:
                packages[name] = 0  # Se completara con downloads reales

        # Fase 3: Obtener download counts reales via bulk API
        # La API de npm downloads soporta bulk queries (hasta 128 paquetes)
        names_needing_downloads = list(packages.keys())[:count]
        print(f"  Fetching download counts for {len(names_needing_downloads)} packages...")

        batch_size = 128
        for i in range(0, len(names_needing_downloads), batch_size):
            batch = names_needing_downloads[i : i + batch_size]

            # Filtrar paquetes con @ (scoped packages necesitan encoding)
            # y paquetes con nombres problematicos
            simple_batch = [n for n in batch if "/" not in n]
            scoped_batch = [n for n in batch if "/" in n]

            # Bulk download para non-scoped packages
            if simple_batch:
                try:
                    bulk_name = ",".join(simple_batch)
                    resp = client.get(
                        f"https://api.npmjs.org/downloads/point/last-week/{bulk_name}"
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # Bulk response: {package_name: {downloads: N, ...}, ...}
                        for pkg_name, pkg_data in data.items():
                            if isinstance(pkg_data, dict) and "downloads" in pkg_data:
                                packages[pkg_name] = pkg_data["downloads"]
                except (httpx.HTTPError, json.JSONDecodeError, ValueError):
                    pass

            # Individual download para scoped packages
            for name in scoped_batch:
                try:
                    encoded = name.replace("/", "%2f")
                    resp = client.get(
                        f"https://api.npmjs.org/downloads/point/last-week/{encoded}"
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if "downloads" in data:
                            packages[name] = data["downloads"]
                except (httpx.HTTPError, json.JSONDecodeError, ValueError):
                    pass

            # Rate limiting
            time.sleep(0.1)

    # Filtrar paquetes sin downloads y ordenar por downloads descendente
    packages = {
        k: v
        for k, v in sorted(packages.items(), key=lambda x: x[1], reverse=True)
        if v > 0
    }

    # Limitar al count solicitado
    if len(packages) > count:
        packages = dict(list(packages.items())[:count])

    print(f"  Got {len(packages)} npm packages with download data")
    return packages


def save_json(data: dict[str, int], filepath: Path) -> None:
    """Guarda datos como JSON formateado."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    size_kb = filepath.stat().st_size / 1024
    print(f"  Saved {filepath} ({size_kb:.1f} KB, {len(data)} packages)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch popular packages from PyPI and npm registries.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5000,
        help="Number of top packages to fetch (default: 5000)",
    )
    parser.add_argument(
        "--pypi-only",
        action="store_true",
        help="Only fetch PyPI packages",
    )
    parser.add_argument(
        "--npm-only",
        action="store_true",
        help="Only fetch npm packages",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR,
        help=f"Output directory (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )

    args = parser.parse_args()
    output_dir = args.output_dir
    fetch_both = not args.pypi_only and not args.npm_only

    print(f"Output directory: {output_dir}")
    print()

    if fetch_both or args.pypi_only:
        pypi_data = fetch_pypi_top(count=args.top, timeout=args.timeout)
        if pypi_data:
            save_json(pypi_data, output_dir / "popular_pypi.json")
        else:
            print("  WARNING: No PyPI data fetched", file=sys.stderr)
        print()

    if fetch_both or args.npm_only:
        npm_data = fetch_npm_top(count=args.top, timeout=args.timeout)
        if npm_data:
            save_json(npm_data, output_dir / "popular_npm.json")
        else:
            print("  WARNING: No npm data fetched", file=sys.stderr)
        print()

    print("Done!")


if __name__ == "__main__":
    main()
