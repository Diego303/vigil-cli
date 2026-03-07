# Seguimiento de Implementacion V0 — vigil

> Documento de seguimiento detallado del progreso de implementacion del MVP de vigil.
> Cada fase se actualiza conforme se completa.

---

## Estado General

| Fase | Nombre | Estado | Tests |
|------|--------|--------|-------|
| FASE 0 | Scaffolding + Config + Core | COMPLETADA (QA done) | 350 |
| FASE 1 | Dependency Analyzer | COMPLETADA (QA done) | 282 |
| FASE 2 | Auth & Secrets Analyzers | COMPLETADA (QA done) | 329 |
| FASE 3 | Test Quality Analyzer | COMPLETADA (QA done) | 209 |
| FASE 4 | Reports + Formatters | Pendiente | — |
| FASE 5 | Integration + Testing + Docs | Pendiente | — |
| FASE 6 | Data + Polish | Pendiente | — |

**Metricas actuales:**
- Tests totales: 1170 (todos pasando, 0 warnings)
- Cobertura FASE 3: 98% (349 statements, 7 missed)
- Archivos fuente: 39
- Archivos de test: 41

---

## FASE 0 — Scaffolding + Config + Core

**Objetivo:** Proyecto instalable con `pip install -e .`, CLI responde a `vigil --help`, `vigil scan src/` ejecuta el engine con 0 analyzers y reporta "0 findings".

**Estado: COMPLETADA**

### F0.1 — pyproject.toml y estructura del proyecto

**Archivo:** `pyproject.toml`

- Nombre del paquete: `vigil-ai-cli`
- Version: `0.1.0`
- Python requerido: `>=3.12`
- Dependencias: click>=8.1, pydantic>=2.0, httpx>=0.27, structlog>=24.1, pyyaml>=6.0
- Dependencias dev: pytest>=8.0, pytest-cov>=5.0, ruff>=0.4
- Entry point: `vigil = "vigil.cli:main"`
- Build system: setuptools con `src/` layout

**Decision:** Se omitio `tomli` del plan original. Python 3.12+ incluye `tomllib` en la stdlib; `tomli` solo se necesitaria como fallback para Python <3.11, que no soportamos. Se usara `tomllib` directamente cuando se implemente el parser de `pyproject.toml` en FASE 1.

**Estructura creada:**
```
src/vigil/
  __init__.py, __main__.py, cli.py
  config/    (schema.py, loader.py, rules.py)
  core/      (finding.py, engine.py, file_collector.py, rule_registry.py)
  analyzers/ (base.py)
  reports/   (formatter.py, human.py, json_fmt.py, junit.py, sarif.py, summary.py)
  logging/   (setup.py)
tests/
  conftest.py, test_cli.py
  test_config/ (test_schema.py, test_loader.py, test_rules.py)
  test_core/   (test_finding.py, test_engine.py, test_file_collector.py)
  test_reports/ (test_formatters.py)
data/          (vacio, se poblara en FASE 6)
```

### F0.2 — Modelos de datos centrales (Finding, Severity, Category, Location)

**Archivo:** `src/vigil/core/finding.py`

Implementados exactamente segun el plan:
- `Severity(str, Enum)` — CRITICAL, HIGH, MEDIUM, LOW, INFO
- `Category(str, Enum)` — DEPENDENCY, AUTH, SECRETS, TEST_QUALITY
- `Location` dataclass — file, line, column, end_line, snippet
- `Finding` dataclass — rule_id, category, severity, message, location, suggestion, metadata
- Propiedad `is_blocking` — True si severity es CRITICAL o HIGH

**Tests:** 12 tests en `test_finding.py`
- Valores de enums, construccion desde string
- Creacion de Finding con todos los campos
- `is_blocking` para cada nivel de severidad
- Metadata vacia por defecto

### F0.3 — ScanEngine y ScanResult

**Archivo:** `src/vigil/core/engine.py`

`ScanResult` dataclass con:
- Contadores por severidad: `critical_count`, `high_count`, `medium_count`, `low_count`
- `has_blocking_findings` — any finding con CRITICAL o HIGH
- `findings_above(threshold)` — filtra findings >= severidad dada

`ScanEngine` orquestador:
- `register_analyzer()` — registra un analyzer
- `run(paths)` — flujo completo: collect files -> run analyzers -> apply overrides -> sort findings
- `_should_run()` — filtra analyzers por categoria si hay filtro activo
- `_apply_rule_overrides()` — aplica enabled/disabled y severity overrides desde config
- Errores de un analyzer se capturan y agregan a `ScanResult.errors` sin crashear el scan

**Decision:** Se agrego filtrado por `exclude_rules` (lista de rule IDs a excluir) que el plan original no contemplaba explicitamente pero es necesario para el flag `--exclude-rule` del CLI.

**Tests:** 12 tests en `test_engine.py`
- ScanResult vacio, contadores, `findings_above` con distintos thresholds
- Engine sin analyzers (0 findings)
- Engine con analyzer fake que retorna findings
- Error en analyzer no crashea el scan
- Findings ordenados por severidad
- Rule override: deshabilitar regla, cambiar severidad
- Filtro por exclude_rules
- Filtro por categoria

### F0.4 — File Collector

**Archivo:** `src/vigil/core/file_collector.py`

- `collect_files(paths, include, exclude, languages)` — recopila archivos recursivamente
- Filtrado por extension segun lenguaje (`.py` para Python, `.js/.ts/.jsx/.tsx/.mjs/.cjs` para JavaScript)
- Patrones de exclusion (node_modules, .venv, __pycache__, etc.)
- Siempre incluye archivos de dependencias (requirements.txt, pyproject.toml, package.json) independientemente del filtro de lenguaje
- Deduplicacion preservando orden
- Soporte para paths individuales (archivos) ademas de directorios

**Tests:** 11 tests en `test_file_collector.py`
- Filtrado por lenguaje (Python, JavaScript, ambos)
- Exclusion de patrones (.venv)
- Inclusion de archivos de dependencias
- Path individual, path inexistente, directorio vacio
- Directorios anidados
- Deduplicacion

### F0.5 — Configuracion (Schema + Loader)

**Archivos:** `src/vigil/config/schema.py`, `src/vigil/config/loader.py`

**Schema Pydantic v2:**
- `ScanConfig` — modelo principal con include, exclude, test_dirs, fail_on, languages
- `DepsConfig` — verify_registry, min_age_days, min_weekly_downloads, similarity_threshold, cache_ttl_hours, offline_mode
- `AuthConfig` — max_token_lifetime_hours, require_auth_on_mutating, cors_allow_localhost
- `SecretsConfig` — min_entropy, check_env_example, placeholder_patterns (12 patterns por defecto)
- `TestQualityConfig` — min_assertions_per_test, detect_trivial_asserts, detect_mock_mirrors
- `OutputConfig` — format, output_file, colors, verbose, show_suggestions
- `RuleOverride` — enabled (bool|None), severity (str|None)
- Campos de runtime agregados a `ScanConfig`: categories, rules_filter, exclude_rules

**Loader:**
- `find_config_file()` — busca .vigil.yaml/.vigil.yml subiendo por el arbol de directorios
- `load_config()` — merge de tres capas: defaults <- YAML <- CLI overrides
- `_merge_cli_overrides()` — integra flags del CLI al dict de config
- `generate_config_yaml()` — genera contenido YAML para `vigil init`
- Presets: strict (fail_on=medium, min_age=60, max_token=1h), standard (defaults), relaxed (fail_on=critical, min_age=7, max_token=72h)

**Tests:** 26 tests en `test_schema.py` + `test_loader.py`
- Valores por defecto de todos los modelos
- Valores custom
- Rule overrides
- Busqueda de config: directorio actual, subida por arbol
- Carga desde YAML con secciones anidadas
- CLI overrides sobre YAML
- Config inexistente, YAML invalido, YAML vacio
- Generacion de config por estrategia

### F0.6 — Catalogo de reglas y Rule Registry

**Archivos:** `src/vigil/config/rules.py`, `src/vigil/core/rule_registry.py`

**Catalogo (RULES_V0):** 26 reglas definidas como `RuleDefinition` dataclass:
- 7 reglas DEP (Dependency Hallucination) — con refs OWASP LLM03, CWE-829
- 7 reglas AUTH (Auth & Permission Patterns) — con refs CWE-306, CWE-862, CWE-798, CWE-942, CWE-614, CWE-208
- 6 reglas SEC (Secrets & Credentials) — con ref CWE-798
- 6 reglas TEST (Test Quality)

**RuleRegistry:**
- Carga todas las reglas built-in al inicializar
- `get(rule_id)` — lookup por ID
- `all()` — todas las reglas
- `by_category()`, `by_severity()` — filtrado
- `enabled_rules(overrides)` — reglas habilitadas considerando overrides

**Tests:** 14 tests en `test_rules.py`
- Todos los campos obligatorios presentes
- IDs unicos
- Formato de ID (REGEX `^[A-Z]+-\d{3}$`)
- Todas las categorias cubiertas
- Conteo de reglas por categoria
- Registry: carga, lookup, filtrado, reglas habilitadas con overrides

### F0.7 — BaseAnalyzer Protocol

**Archivo:** `src/vigil/analyzers/base.py`

Protocolo (typing.Protocol) con:
- Propiedad `name: str`
- Propiedad `category: Category`
- Metodo `analyze(files: list[str], config: ScanConfig) -> list[Finding]`

No requiere tests propios — se valida indirectamente via tests del ScanEngine con `FakeAnalyzer`.

### F0.8 — Report Formatters

**Archivos:** `src/vigil/reports/formatter.py`, `human.py`, `json_fmt.py`, `junit.py`, `sarif.py`, `summary.py`

**Decision:** El plan original situa los formatters en FASE 4, pero se implementaron en FASE 0 porque el CLI necesita al menos el formatter human para mostrar output. Se implementaron los 4 formatos completos ya que son modulos independientes y relativamente simples.

**Formatter factory:**
- `get_formatter(format_name)` — retorna el formatter apropiado con lazy imports

**Human formatter:**
- Header con version y conteo de archivos
- Findings con icono de severidad, colores ANSI, rule_id, location, message, suggestion
- Resumen estadistico: archivos, findings por severidad, analyzers ejecutados
- Deteccion automatica de soporte de colores (isatty)

**JSON formatter:**
- Output estructurado con version, files_scanned, duration, findings, errors
- Cada finding serializado con rule_id, category, severity, message, location, suggestion, metadata

**JUnit XML formatter:**
- Formato compatible con CI dashboards
- Un testcase por finding, con failure type (error para CRITICAL/HIGH, warning para MEDIUM/LOW)
- Testcase exitoso cuando no hay findings

**SARIF 2.1.0 formatter:**
- Compatible con GitHub Code Scanning y GitLab SAST
- Incluye tool.driver.rules con metadata de las reglas usadas
- Cada finding mapeado a result con ruleId, level, message, locations
- Niveles SARIF: CRITICAL/HIGH -> error, MEDIUM -> warning, LOW/INFO -> note

**Summary builder:**
- Breakdown por severidad, categoria y regla
- Flags: has_blocking, total_findings, errors

**Tests:** 19 tests en `test_formatters.py`
- Factory: todos los formatos validos + formato desconocido
- Human: resultado vacio, con findings, con errores, suggestions visibles
- JSON: resultado vacio, con findings, JSON valido
- JUnit: resultado vacio, con findings, XML valido
- SARIF: resultado vacio, con findings, schema presente, tool info
- Summary: vacio, con findings

### F0.9 — CLI completa

**Archivo:** `src/vigil/cli.py`

5 subcomandos implementados:

**`vigil scan [PATHS]`** — Scan principal con todas las opciones:
- `--config, -c` — ruta a config YAML
- `--format, -f` — human/json/junit/sarif
- `--output, -o` — archivo de salida
- `--fail-on` — threshold de severidad (critical/high/medium/low)
- `--category, -C` — filtro por categoria (multiple)
- `--rule, -r` — solo reglas especificas (multiple)
- `--exclude-rule, -R` — excluir reglas (multiple)
- `--language, -l` — solo lenguajes especificos (multiple)
- `--offline` — sin HTTP requests
- `--changed-only` — solo archivos cambiados (git diff)
- `--verbose, -v` — output detallado
- `--quiet, -q` — solo findings

**`vigil deps [PATH]`** — Solo dependencias con `--verify/--no-verify`

**`vigil tests [PATHS]`** — Solo calidad de tests con `--min-assertions`

**`vigil init [PATH]`** — Genera .vigil.yaml con `--strategy` y `--force`

**`vigil rules`** — Lista todas las reglas agrupadas por categoria

**Decision:** Se agrego validacion de directorio en `init` — el plan original no preveia el caso de directorio inexistente, que causaba `FileNotFoundError`.

**`--changed-only` implementacion:** Usa `git diff --name-only HEAD` con fallback a `git status --porcelain`. Timeout de 10s. Graceful failure si git no esta disponible.

**Tests:** 19 tests en `test_cli.py`
- help, version
- scan: directorio actual, inexistente, json/sarif/junit, output a archivo, config custom
- deps: help, ejecucion basica
- tests: help
- rules: lista todas las reglas
- init: crea config, no sobreescribe sin --force, --force funciona, estrategia strict, directorio inexistente

### F0.10 — Logging

**Archivo:** `src/vigil/logging/setup.py`

- `setup_logging(verbose)` — configura structlog con output a stderr
- Modo verbose: nivel DEBUG, ConsoleRenderer completo
- Modo normal: nivel WARNING, renderer minimalista
- Logs nunca se mezclan con output de findings (stderr vs stdout)

### F0.11 — Archivos de soporte

- `.vigil.example.yaml` — configuracion de ejemplo documentada
- `.gitignore` — exclusiones para Python, venvs, IDEs, cache, testing

### F0.QA — Auditoria de calidad y tests adicionales

**Estado: COMPLETADA**

Se realizo una auditoria exhaustiva del codigo de FASE 0 con el rol de ingeniero senior de QA. Se encontraron 15 hallazgos (6 bugs, 4 robustez, 2 consistencia, 3 menores) y se corrigieron los 6 bugs.

**Bugs corregidos:**

1. **`file_collector.py:96`** — Exclude usaba substring match (`"build" in path_str`), lo que causaba que `"build/"` excluyera tambien `"rebuild/"`. Corregido a path-component matching via `file_path.parts`.
2. **`schema.py:56`** — `TestsConfig` causaba `PytestCollectionWarning` porque pytest intentaba recolectarla como clase de test. Renombrada a `TestQualityConfig` + `__test__ = False`.
3. **`schema.py:94`** — `fail_on` era `str` sin validacion, aceptaba cualquier valor como `"banana"` que luego causaba `ValueError` en el CLI. Cambiado a `Literal["critical","high","medium","low","info"]`.
4. **`loader.py:164`** — `generate_config_yaml` producia listas en sintaxis Python (`['src/', 'lib/']`) que no es YAML valido. Creado helper `_yaml_list()` que genera `["src/", "lib/"]` (flow sequence YAML valido). Ahora el roundtrip `vigil init` -> `load_config` funciona.
5. **`sarif.py:56`** — `rule.name.replace(" ", "")` generaba `"Hallucinateddependency"` en vez de PascalCase. Corregido a `"".join(w.capitalize() for w in name.split())` -> `"HallucinatedDependency"`.
6. **`cli.py:133`** — `--output reports/scan.json` fallaba con `FileNotFoundError` si el directorio padre no existia. Agregado `parent.mkdir(parents=True, exist_ok=True)` antes de escribir.

**Issues documentados (no corregidos, para fases futuras):**

- `engine.py`: campo `include` en `ScanConfig` existe pero nunca se pasa a `collect_files` — no tiene efecto
- `cli.py`: `_get_changed_files` no maneja filenames con espacios en git status `--porcelain`
- `rules.py`: `DEP-007` y `SEC-006` son CRITICAL sin `cwe_ref` asignado

**Tests nuevos: 225 tests en 9 archivos:**

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_core/test_finding_edge_cases.py` | 16 | Severity/Category como string, metadata aislamiento, `is_blocking` parametrizado |
| `test_core/test_engine_edge_cases.py` | 17 | Multi-analyzer, error recovery, overrides combinados, sort estable |
| `test_core/test_file_collector_edge_cases.py` | 25 | Exclude por componente, extensiones JS, dep files, symlinks, binarios |
| `test_config/test_schema_edge_cases.py` | 12 | Validacion `fail_on`, aislamiento de defaults, override parcial nested |
| `test_config/test_loader_edge_cases.py` | 24 | YAML edge cases, merge logic, roundtrip, presets |
| `test_config/test_rules_edge_cases.py` | 20 | Integridad catalogo, IDs secuenciales, severidades vs plan, CWE refs |
| `test_reports/test_formatters_edge_cases.py` | 28 | Todos los formatters: chars especiales, unicode, SARIF severity mapping |
| `test_cli_edge_cases.py` | 34 | Todos los commands/flags, formatos, exit codes, output nested dirs |
| `test_integration.py` | 14 | Pipeline completo scan, todos los formatters con datos realistas |
| `test_logging.py` | 3 | Niveles de log, idempotencia |

**1 test existente actualizado:** `test_config/test_schema.py` — `TestsConfig` -> `TestQualityConfig`

**Cobertura por modulo:**

| Modulo | Cobertura |
|--------|-----------|
| `core/finding.py` | 100% |
| `core/engine.py` | 99% |
| `core/file_collector.py` | 100% |
| `config/schema.py` | 100% |
| `config/rules.py` | 100% |
| `config/loader.py` | 95% |
| `reports/*` | 95-100% |
| `cli.py` | 81% |
| `logging/setup.py` | 100% |

---

## FASE 1 — Dependency Analyzer

**Objetivo:** Implementar el analyzer de dependencias que detecta paquetes alucinados, typosquatting, paquetes nuevos sospechosos, versiones inexistentes y paquetes sin repositorio fuente.

**Estado: COMPLETADA**

### F1.1 — Parsers de dependencias

**Archivo:** `src/vigil/analyzers/deps/parsers.py`

- `DeclaredDependency` dataclass — name, version_spec, source_file, line_number, ecosystem, is_dev
- `parse_requirements_txt()` — parsea requirements.txt/requirements-dev.txt con soporte para extras, version specs, comentarios, flags (`-r`, `-i`)
- `parse_pyproject_toml()` — parsea `[project.dependencies]` y `[project.optional-dependencies]` usando `tomllib` (stdlib 3.11+) con fallback a `tomli`
- `parse_package_json()` — parsea `dependencies` y `devDependencies`
- `find_and_parse_all()` — descubre y parsea todos los archivos de dependencias con `os.walk` + pruning de directorios (.venv, node_modules, .git, etc.)
- Helpers: `_build_toml_line_map()`, `_find_json_key_line()` para rastreo de numeros de linea

**Decision:** Se usa `os.walk()` con pruning in-place (`dirnames[:] = [...]`) en vez de `rglob()` para evitar recorrer `.venv/` y `node_modules/`, lo cual causaba timeouts de >2 minutos en WSL.

**Tests:** 40 tests en `test_analyzers/test_deps/test_parsers.py`
- requirements.txt: paquetes con version, sin version, con extras, comentarios, lineas vacias, flags -r/-i, encoding errors
- pyproject.toml: dependencies, optional-dependencies (dev/non-dev), extras, TOML invalido, sin seccion project
- package.json: dependencies, devDependencies, version types, JSON invalido
- find_and_parse_all: multiples archivos, pruning de directorios, directorio inexistente

### F1.2 — Registry Client

**Archivo:** `src/vigil/analyzers/deps/registry_client.py`

- `PackageInfo` dataclass — name, version, exists, description, home_page, source_repo, created_at (ISO string), latest_version
  - Propiedades: `created_datetime`, `age_days`
- `RegistryClient` clase — cliente HTTP para PyPI y npm con cache en disco
  - Cache en `~/.cache/vigil/registry/` con TTL configurable (default 24h)
  - Inicializacion lazy del cliente httpx (solo se crea al primer request)
  - Context manager support (`async with` / close)
  - `check_package(name, ecosystem)` — verifica existencia en PyPI o npm
  - `check_version(name, version, ecosystem)` — verifica existencia de version especifica
  - Errores de red asumen que el paquete existe (evita falsos positivos)
  - Cache key: `{ecosystem}/{normalized_name}.json`

**Decision:** `created_at` se almacena como string ISO en vez de datetime para serializacion JSON directa al cache. La propiedad `created_datetime` parsea bajo demanda.

**Tests:** 21 tests en `test_analyzers/test_deps/test_registry_client.py`
- PackageInfo: propiedades, age_days, created_datetime, paquete inexistente
- RegistryClient: check_package PyPI/npm (con mock httpx), cache hit/miss, TTL expirado
- check_version: version existente/inexistente, paquete inexistente
- Errores de red: timeout, connection error (asumen paquete existe)
- Modo offline: skip HTTP, close() limpieza

### F1.3 — Similarity checker

**Archivo:** `src/vigil/analyzers/deps/similarity.py`

- `levenshtein_distance(s1, s2)` — implementacion O(min(m,n)) en espacio
- `normalized_similarity(s1, s2)` — similitud 0.0-1.0 basada en distancia Levenshtein
- `_normalize_package_name(name, ecosystem)` — normalizacion PyPI (PEP 503: hyphens/underscores/dots equivalentes, lowercase)
- `load_popular_packages(ecosystem, data_dir)` — carga corpus desde archivos en `data/`, fallback a corpus builtin
- `find_similar_popular(name, ecosystem, threshold, popular)` — encuentra paquetes populares similares por encima del threshold
- Corpus builtin: ~100 paquetes PyPI + ~70 paquetes npm como fallback hasta que FASE 6 genere archivos completos

**Decision:** El threshold por defecto es 0.85 (configurable via `deps.similarity_threshold`). Esto captura typos de un caracter como "requets" (0.875) pero no transposiciones dobles como "reqeusts" (0.75), lo cual es intencionalmente conservador para evitar falsos positivos.

**Tests:** 34 tests en `test_analyzers/test_deps/test_similarity.py`
- Levenshtein: strings iguales, vacios, un vacio, un caracter diferente, longitudes distintas
- Similitud normalizada: identicos=1.0, completamente distintos=0.0, similar alto/bajo
- Normalizacion: PyPI (hyphens, underscores, dots, mixed case), npm (sin cambio)
- Corpus: load_popular_packages (builtin fallback, data files), formato correcto
- find_similar_popular: match, no match, threshold variable, normalizacion

### F1.4 — DependencyAnalyzer

**Archivo:** `src/vigil/analyzers/deps/analyzer.py`

- `DependencyAnalyzer` — implementa `BaseAnalyzer` Protocol
  - `name = "dependency"`, `category = Category.DEPENDENCY`
  - `analyze(files, config)` — flujo completo de analisis de dependencias
- Reglas implementadas:
  - **DEP-001** (CRITICAL) — Paquete no existe en registro (alucinado)
  - **DEP-002** (HIGH) — Paquete creado hace menos de N dias (configurable, default 30)
  - **DEP-003** (HIGH) — Nombre similar a paquete popular (typosquatting)
  - **DEP-005** (MEDIUM) — Paquete sin repositorio fuente vinculado
  - **DEP-007** (CRITICAL) — Version especificada no existe en registro
- Helpers: `_extract_roots()` (infiere directorios raiz de la lista de archivos), `_deduplicate_deps()` (por nombre+ecosistema), `_extract_pinned_version()` (extrae version exacta de specs como `==1.0.0`)
- Pre-carga corpus de paquetes populares una sola vez para todas las verificaciones de similitud

**Reglas diferidas:**
- **DEP-004** (unpopular) — requiere API de estadisticas de descargas (no disponible en metadata basica de PyPI/npm)
- **DEP-006** (missing import) — requiere parser de imports AST, fuera de scope V0 (regex-based)

**Decision:** Se deduplicaron dependencias por nombre+ecosistema antes de verificar, para evitar queries duplicados al registro cuando el mismo paquete aparece en multiples archivos (ej: requirements.txt y pyproject.toml).

**Tests:** 25 tests en `test_analyzers/test_deps/test_analyzer.py`
- Propiedades: name, category
- DEP-001: paquete inexistente genera finding CRITICAL
- DEP-002: paquete nuevo genera finding HIGH
- DEP-003: typosquatting genera finding HIGH
- DEP-005: sin source repo genera finding MEDIUM
- DEP-007: version inexistente genera finding CRITICAL
- Paquete limpio: no genera findings
- Modo offline: sin HTTP, solo checks estaticos
- Deduplicacion: mismo paquete en multiples archivos
- Helpers: _extract_roots, _deduplicate_deps, _extract_pinned_version

### F1.5 — Wiring al CLI y performance

**Archivos modificados:** `src/vigil/cli.py`, `src/vigil/core/file_collector.py`

**CLI:**
- Nueva funcion `_register_analyzers(engine)` que registra `DependencyAnalyzer` en el engine
- Reemplazados 3 placeholders (`# TODO: register analyzers`) en comandos `scan`, `deps`, `check_tests` con llamada a `_register_analyzers(engine)`

**File collector:**
- Reemplazado `Path.rglob("*")` con `os.walk()` + pruning in-place de directorios excluidos
- Critico para performance en WSL: scan paso de >2 minutos a ~0.3 segundos

**Tests CLI actualizados:**
- Agregado `--offline` a todos los tests que escanean `.` (directorio real del repo) para evitar llamadas HTTP a PyPI/npm
- Archivos afectados: `test_cli.py` (~8 tests), `test_cli_edge_cases.py` (~20 tests)

### F1.Fixtures — Test fixtures

**Archivos creados en `tests/fixtures/deps/`:**

- `valid_project/requirements.txt` — requests, flask con versiones pinneadas
- `valid_project/pyproject.toml` — click, pydantic en [project.dependencies]
- `hallucinated_deps/requirements.txt` — paquete inventado "flask-nonexistent-xyz"
- `hallucinated_deps/pyproject.toml` — paquete inventado "nonexistent-ai-helper"
- `npm_project/package.json` — express + dependencia inventada "react-nonexistent-xyz"

### Resumen de tests FASE 1

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_analyzers/test_deps/test_parsers.py` | 40 | ~95% parsers.py |
| `test_analyzers/test_deps/test_registry_client.py` | 21 | ~92% registry_client.py |
| `test_analyzers/test_deps/test_similarity.py` | 34 | ~95% similarity.py |
| `test_analyzers/test_deps/test_analyzer.py` | 25 | ~90% analyzer.py |
| **Total FASE 1** | **120** | **~92%** |

### F1.QA — Auditoria de calidad y tests adicionales

**Estado: COMPLETADA**

Se realizo una auditoria exhaustiva del codigo de FASE 1 con el rol de ingeniero senior de QA. Se encontraron 11 hallazgos (4 bugs, 4 robustez, 3 consistencia/seguridad) y se corrigieron los 4 bugs.

**Bugs corregidos:**

1. **`similarity.py:287`** — Corpus builtin de npm tenia entrada duplicada para `"chalk"` (linea 287 con 300K sobreescribia linea 242 con 22M descargas). Eliminada la entrada duplicada.
2. **`engine.py:_apply_rule_overrides`** — El flag `--rule` (`rules_filter` en ScanConfig) nunca filtraba findings realmente. Agregado filtrado explicito: si `rules_filter` esta activo, solo se incluyen findings cuyo `rule_id` esta en la lista.
3. **`parsers.py:parse_requirements_txt`** — Dependencias con environment markers (ej: `pywin32; sys_platform == "win32"`) eran silenciosamente ignoradas porque el `;` confundia el regex. Agregado strip de markers antes del parsing.
4. **`analyzer.py:_extract_roots`** — Retornaba `["."]` para input vacio, causando que el analyzer escaneara el directorio de trabajo actual inesperadamente. Cambiado a retornar `[]` con early return en `analyze()`.

**Issues documentados (no corregidos, para fases futuras):**

- `registry_client.py`: No valida que `created_at` sea un ISO string valido antes de parsear
- `similarity.py`: Corpus builtin es conservador (~170 paquetes), se ampliara en FASE 6
- `analyzer.py`: DEP-004 (descargas) y DEP-006 (imports sin declarar) diferidos a fases futuras

**Tests nuevos: 162 tests en 5 archivos + updates a 2 existentes:**

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_analyzers/test_deps/test_parsers_qa.py` | 28 | Environment markers, BOM, CRLF, Unicode, URLs, fixtures |
| `test_analyzers/test_deps/test_registry_client_qa.py` | 26 | PackageInfo edge cases, cache, sanitize key, response parsing |
| `test_analyzers/test_deps/test_similarity_qa.py` | 27 | Corpus integrity, Levenshtein edges, PEP 503, false positives |
| `test_analyzers/test_deps/test_analyzer_qa.py` | 32 | False positives/negatives, boundary conditions, metadata |
| `test_analyzers/test_deps/test_integration_qa.py` | 13 | Engine+Analyzer, CLI+deps, regression tests |
| `test_cli.py` (actualizado) | — | Refactored to use tmp_path (avoid fixture interference) |
| `test_cli_edge_cases.py` (actualizado) | — | Refactored to use clean_dir fixture |

**Fixtures nuevas en `tests/fixtures/deps/`:**

- `clean_project/` — requirements.txt, pyproject.toml, package.json con dependencias legitimas
- `vulnerable_project/` — mix de dependencias legitimas y sospechosas (typosquatting, inexistentes)
- `edge_cases/` — empty, comments-only, markers, URLs, malformed JSON/TOML

**Tests CLI refactorizados:**

Se refactorizaron `test_cli.py` y `test_cli_edge_cases.py` para que todos los tests usen `tmp_path` con archivos limpios en vez de escanear el directorio raiz del proyecto (`.`). Esto evita interferencia de fixtures de test y hace los tests deterministicos.

**Cobertura por modulo post-QA:**

| Modulo | Cobertura |
|--------|-----------|
| `analyzers/deps/parsers.py` | ~97% |
| `analyzers/deps/registry_client.py` | ~95% |
| `analyzers/deps/similarity.py` | ~97% |
| `analyzers/deps/analyzer.py` | ~93% |
| `core/engine.py` | 99% |
| `cli.py` | ~85% |

**Totales post-QA FASE 1:**
- Tests FASE 1: 282 (120 originales + 162 QA)
- Tests totales proyecto: 632
- Cobertura global: ~94%

---

## FASE 2 — Auth & Secrets Analyzers

**Objetivo:** Implementar los analyzers de auth patterns (AUTH-001 a AUTH-007) y secrets (SEC-001 a SEC-006) con deteccion regex para Python (FastAPI/Flask) y JavaScript (Express).

**Estado: COMPLETADA**

### F2.1 — AuthAnalyzer

**Archivos:**
- `src/vigil/analyzers/auth/__init__.py` — Package init, exporta AuthAnalyzer
- `src/vigil/analyzers/auth/analyzer.py` — AuthAnalyzer orquestador
- `src/vigil/analyzers/auth/patterns.py` — Regex patterns compilados
- `src/vigil/analyzers/auth/endpoint_detector.py` — Deteccion de endpoints HTTP
- `src/vigil/analyzers/auth/middleware_checker.py` — Verificacion de auth en endpoints

**AuthAnalyzer** — implementa `BaseAnalyzer` Protocol:
- `name = "auth"`, `category = Category.AUTH`
- `analyze(files, config)` — itera archivos relevantes (.py, .js, .jsx, .ts, .tsx, .mjs, .cjs), detecta endpoints y ejecuta checks linea por linea
- Reglas implementadas:
  - **AUTH-001** (HIGH) — Endpoint con path sensible sin auth (GET /admin, /users, /billing, etc.)
  - **AUTH-002** (HIGH) — Endpoint mutante (POST/PUT/DELETE/PATCH) sin auth
  - **AUTH-003** (MEDIUM) — JWT con lifetime excesivo (>24h por defecto, configurable)
  - **AUTH-004** (CRITICAL) — JWT/auth secret hardcodeado con baja entropy (<4.0 bits/char)
  - **AUTH-005** (HIGH) — CORS configurado con `*` (FastAPI, Flask, Express)
  - **AUTH-006** (MEDIUM) — Cookie sin flags de seguridad (httpOnly, secure, sameSite)
  - **AUTH-007** (MEDIUM) — Comparacion de passwords sin timing-safe function

**Endpoint detector:**
- `DetectedEndpoint` dataclass — file, line, method, path, framework, snippet, has_auth
- FastAPI: `@app.get("/path")`, `@router.post("/path")` con context scan para `Depends(get_current_user)`, `Security()`
- Flask: `@app.route("/path", methods=["GET"])` con scan para `@login_required`, `@auth_required`, etc.
- Express: `app.get('/path', handler)` con inline scan para auth middleware names
- Soporte para `window` de contexto configurable (lineas antes/despues del decorator)

**Middleware checker:**
- `SENSITIVE_PATH_PATTERNS` — 13 patrones: /admin, /user, /users, /account, /profile, /settings, /billing, /payment, /order, /api/v, /private, /internal, /dashboard
- `check_endpoint_auth()` — retorna AUTH-001 o AUTH-002 segun el tipo de endpoint
- Sugerencias framework-specific en cada finding

**Patterns:**
- JWT lifetime: `_JWT_TIMEDELTA_HOURS` (Python timedelta), `_JWT_EXPIRES_IN_JS` (expiresIn con unidades), `_JWT_EXPIRES_IN_SECONDS` (expiresIn numerico)
- Hardcoded secrets: `_HARDCODED_SECRET_PY` / `_HARDCODED_SECRET_JS` con filtrado de env references
- CORS: `_CORS_FASTAPI` / `_CORS_FLASK` / `_CORS_EXPRESS_STAR` / `_CORS_EXPRESS_DEFAULT`
- Cookies: `_COOKIE_SECURE_FLAG` / `_COOKIE_HTTPONLY_FLAG` / `_COOKIE_SAMESITE_FLAG`
- Password: `_PW_COMPARE_PY` / `_PW_COMPARE_JS` / `_TIMING_SAFE`

**Configuracion:** `AuthConfig` con:
- `max_token_lifetime_hours` (default 24) — threshold para AUTH-003
- `require_auth_on_mutating` (default True) — habilita/deshabilita AUTH-002
- `cors_allow_localhost` (default True) — suprime AUTH-005 en archivos dev/test/local/example

**Tests:** 132 tests (66 originales + 66 QA)

| Archivo | Tests |
|---------|-------|
| `test_auth/test_analyzer.py` | 26 |
| `test_auth/test_endpoint_detector.py` | 21 |
| `test_auth/test_middleware_checker.py` | 13 |
| `test_auth/test_patterns.py` | 30 |
| `test_auth/test_qa_regression.py` | 66 |

### F2.2 — SecretsAnalyzer

**Archivos:**
- `src/vigil/analyzers/secrets/__init__.py` — Package init, exporta SecretsAnalyzer
- `src/vigil/analyzers/secrets/analyzer.py` — SecretsAnalyzer orquestador
- `src/vigil/analyzers/secrets/placeholder_detector.py` — Deteccion de valores placeholder
- `src/vigil/analyzers/secrets/entropy.py` — Calculo de entropy de Shannon
- `src/vigil/analyzers/secrets/env_tracer.py` — Trazado de valores de .env.example

**SecretsAnalyzer** — implementa `BaseAnalyzer` Protocol:
- `name = "secrets"`, `category = Category.SECRETS`
- `analyze(files, config)` — carga env examples, itera archivos, ejecuta checks SEC-001 a SEC-006
- Reglas implementadas:
  - **SEC-001** (CRITICAL) — Valor placeholder (changeme, your-api-key-here, TODO, etc.) en asignacion de secret
  - **SEC-002** (CRITICAL) — Secret hardcodeado con baja entropy (< min_entropy configurable)
  - **SEC-003** (CRITICAL) — Connection string con credenciales embebidas (postgresql, mongodb, redis, amqp, etc.)
  - **SEC-004** (HIGH) — Variable de entorno sensible con valor default hardcodeado
  - **SEC-006** (CRITICAL) — Valor copiado textualmente de .env.example al codigo
- **SEC-005** diferido — requiere parsing de .gitignore, fuera de scope V0

**Placeholder detector:**
- `DEFAULT_PLACEHOLDER_PATTERNS` — 30 regex patterns (changeme, your-*-here, TODO, FIXME, xxx+, sk-your, pk_test, secret123, etc.)
- `_COMPILED_DEFAULT_PATTERNS` — cache compilado a nivel de modulo (evita recompilacion)
- `_SECRET_ASSIGNMENT_PATTERNS` — 3 regex para deteccion de asignaciones (Python, JS const/let/var, object properties)
- `is_placeholder_value()` — verifica si un valor matchea algun patron
- `find_secret_assignments()` — encuentra valores de secrets asignados en una linea

**Entropy:**
- `shannon_entropy()` — bits por caracter usando Counter + log2
- `is_high_entropy_secret()` — len >= 8 y entropy >= threshold
- `is_low_entropy_secret()` — len >= 3 y entropy < threshold

**Env tracer:**
- `ENV_EXAMPLE_FILES` — 6 nombres: .env.example, .env.sample, .env.template, .env.defaults, env.example, env.sample
- `_GENERIC_VALUES` — set de valores demasiado genericos para trazar (true, false, ports, environments)
- `parse_env_example()` — parsea KEY=value, quita comillas, ignora genericos y variable references
- `find_env_values_in_code()` — busca valores exactos en strings del codigo, min longitud 5

**Connection strings:**
- `_CONNECTION_STRING_PATTERNS` — 3 regex: postgresql/mysql/mongodb/redis/amqp, mongodb+srv, sqlserver/mssql
- Password redaction en snippets via `_redact_password()` (seguridad del propio vigil)

**Configuracion:** `SecretsConfig` con:
- `min_entropy` (default 3.0) — threshold para SEC-002
- `check_env_example` (default True) — habilita/deshabilita SEC-006
- `placeholder_patterns` (30 patterns) — patrones de placeholder customizables

**Tests:** 197 tests (126 originales + 71 QA)

| Archivo | Tests |
|---------|-------|
| `test_secrets/test_analyzer.py` | 32 |
| `test_secrets/test_entropy.py` | 17 |
| `test_secrets/test_env_tracer.py` | 21 |
| `test_secrets/test_placeholder_detector.py` | 25 |
| `test_secrets/test_qa_regression.py` | 71 |

### F2.3 — Wiring al CLI

**Archivo modificado:** `src/vigil/cli.py`

- `_register_analyzers()` actualizado para registrar `AuthAnalyzer` y `SecretsAnalyzer` ademas de `DependencyAnalyzer`
- Los tres analyzers se ejecutan en `vigil scan` por defecto
- Filtrado por `--category auth` o `--category secrets` funciona correctamente

### F2.Fixtures — Test fixtures

**Archivos creados:**

`tests/fixtures/auth/`:
- `insecure_fastapi.py` — FastAPI con CORS *, hardcoded secret, JWT 72h, DELETE sin auth, path sensible
- `insecure_flask.py` — Flask con CORS *, hardcoded secret, DELETE sin auth, cookie insegura, password comparison
- `insecure_express.js` — Express con cors() default, hardcoded secret, DELETE sin auth, JWT 72h, cookie insegura
- `secure_app.py` — FastAPI segura: env vars, CORS especifico, JWT 1h, auth en endpoints
- `edge_cases.py` — JWT con days, threshold exacto, timing-safe, cookie parcial

`tests/fixtures/secrets/`:
- `insecure_secrets.py` — Placeholders, low-entropy, connection strings, env defaults
- `insecure_secrets.js` — Version JavaScript de lo anterior
- `.env.example` — Archivo de ejemplo con placeholders
- `copies_env_example.py` — Codigo que copia valores de .env.example
- `secure_code.py` — Uso correcto de env vars, sin hardcoded secrets

### F2.QA — Auditoria de calidad y tests adicionales

**Estado: COMPLETADA**

Se realizo una auditoria exhaustiva del codigo de FASE 2. Se encontraron 15 hallazgos (6 bugs, 4 robustez, 2 consistencia, 3 seguridad) y se corrigieron 9.

**Bugs corregidos:**

1. **`auth/analyzer.py:88,225`** — `auth_config` tipado como `object` en vez de `AuthConfig`. Corregido a `AuthConfig` para type safety.
2. **`auth/analyzer.py:272`** — `import re` dentro del cuerpo de `_check_cookie()`. Movido a import a nivel de modulo.
3. **`secrets/analyzer.py:167-189`** — SEC-006 exponia el valor del secret en el mensaje y metadata del finding. Redactado: solo se muestra el key name y archivo fuente.
4. **`endpoint_detector.py:87`** — `_EXPRESS_AUTH_MIDDLEWARE` regex matcheaba substrings como `auth_header`. Agregados word boundaries `\b`.
5. **`placeholder_detector.py:94-95`** — `is_placeholder_value()` recompilaba todos los patterns en cada llamada sin cache (41x mas lento). Creado `_COMPILED_DEFAULT_PATTERNS` cache a nivel de modulo.
6. **`config/schema.py`** — `SecretsConfig.placeholder_patterns` tenia 12 patterns vs 30 en `DEFAULT_PLACEHOLDER_PATTERNS`. Sincronizados.

**Codigo muerto eliminado:**
- `patterns.py:13` — `AuthPattern` dataclass definido pero nunca usado
- `endpoint_detector.py:45-48` — `_FLASK_METHOD_SHORTCUT` regex definido pero nunca usado
- `secrets/analyzer.py:298-301` — Condicional confuso con `pass` que no tenia efecto

**Issues documentados (no corregidos, para fases futuras):**
- `middleware_checker.py:75` — POST a path sensible reporta AUTH-002 pero no menciona que es un path sensible
- Ambos analyzers duplican `_is_relevant_file`, `_is_comment`, `_read_file_safe` — refactor DRY para FASE 3+
- `_is_comment()` no detecta block comments (`/* */`, `"""`) — limitacion conocida V0
- AUTH-004 y SEC-001 snippets exponen el valor del secret (bajo riesgo para placeholders)

**Tests nuevos: 137 tests en 2 archivos:**

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_auth/test_qa_regression.py` | 66 | Word boundary regression, config typing, CORS path heuristic, false positives/negatives, edge cases, helpers, middleware, patterns, finding quality |
| `test_secrets/test_qa_regression.py` | 71 | SEC-006 no-leakage regression, pattern caching, config sync, false positives/negatives, configuration, edge cases, helpers, entropy, env tracer, finding quality, placeholder detector |

**Cobertura por modulo post-QA:**

| Modulo | Stmts | Miss | Cobertura |
|--------|-------|------|-----------|
| `analyzers/auth/__init__.py` | 2 | 0 | 100% |
| `analyzers/auth/analyzer.py` | 117 | 3 | 97% |
| `analyzers/auth/endpoint_detector.py` | 83 | 1 | 99% |
| `analyzers/auth/middleware_checker.py` | 20 | 0 | 100% |
| `analyzers/auth/patterns.py` | 83 | 2 | 98% |
| `analyzers/secrets/__init__.py` | 2 | 0 | 100% |
| `analyzers/secrets/analyzer.py` | 124 | 3 | 98% |
| `analyzers/secrets/entropy.py` | 21 | 0 | 100% |
| `analyzers/secrets/env_tracer.py` | 61 | 0 | 100% |
| `analyzers/secrets/placeholder_detector.py` | 27 | 0 | 100% |
| **Total FASE 2** | **540** | **9** | **98%** |

**Totales post-QA FASE 2:**
- Tests FASE 2: 329 (192 originales + 137 QA)
- Tests totales proyecto: 961
- Cobertura FASE 2: 98%

---

## FASE 3 — Test Quality Analyzer

**Objetivo:** Implementar el analyzer de calidad de tests que detecta test theater: tests que pasan pero no verifican nada real. Soporta pytest (Python) y jest/mocha (JavaScript/TypeScript).

**Estado: COMPLETADA**

### F3.1 — Coverage heuristics

**Archivo:** `src/vigil/analyzers/tests/coverage_heuristics.py`

- `is_test_file()` — detecta archivos de test por nombre (`test_*.py`, `*_test.py`, `*.test.js`, `*.spec.ts`) y directorio (`tests/`, `__tests__/`, `spec/`)
- `is_python_test_file()` / `is_js_test_file()` — filtros especificos por lenguaje
- `detect_test_framework()` — identifica pytest, unittest, jest o mocha por imports y patrones
- Soporte para extensiones `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`
- Normalizacion de paths Windows (backslash a forward slash)

**Tests:** 20 tests en `test_analyzers/test_tests/test_coverage_heuristics.py`

### F3.2 — Assert checker

**Archivo:** `src/vigil/analyzers/tests/assert_checker.py`

**Extraccion de funciones de test:**
- `extract_python_test_functions()` — extrae `def test_*` y `async def test_*` con heuristica de indentacion, soporta funciones single-line (`def test_x(): assert True`)
- `extract_js_test_functions()` — extrae bloques `test()/it()` con conteo de llaves para determinar fin del bloque
- Retorna tuplas `(nombre, linea_inicio, linea_fin)` para cada funcion

**Conteo de assertions:**
- `count_assertions()` — cuenta assertions en Python (assert, assertEqual, pytest.raises/warns/approx, .should) y JavaScript (expect, assert, .should, .to, .toBe, .toEqual, .toThrow, .rejects, .resolves)
- Ignora lineas de comentario (`#` en Python, `//` en JavaScript)

**Deteccion de patrones:**
- `find_trivial_assertions()` — 10 patrones Python (assert True, assert x, assert x is not None, assertTrue(True), assertIsNotNone, assertIsNone) + 5 patrones JavaScript (toBeTruthy, toBeDefined, not.toBeNull, not.toBeUndefined, toBe(true))
- `find_catch_all_exceptions()` — except Exception/BaseException/bare except con pass (verifica re-raise), JS catch(e)
- `find_skips_without_reason()` — @pytest.mark.skip, @unittest.skip (sin reason), test.skip/it.skip/xit/xtest
- `is_api_test()` — detecta llamadas client.get/post, fetch(), supertest(), axios
- `has_status_code_assertion()` — verifica assertions sobre status_code/.status/.code

**Tests:** 46 tests en `test_analyzers/test_tests/test_assert_checker.py`

### F3.3 — Mock checker

**Archivo:** `src/vigil/analyzers/tests/mock_checker.py`

- `find_mock_return_values()` — detecta `mock.return_value = <literal>`, `@mock.patch(return_value=...)`, `jest.fn().mockReturnValue()`, `.mockResolvedValue()`
- `find_assert_values()` — detecta `assert result == <literal>`, `assertEqual(result, <literal>)`, `expect(result).toBe(<literal>)`
- `find_mock_mirrors()` — cruza valores de mock con valores de assert para detectar mirrors
- `_is_literal()` — valida numeros, strings (con quotes correctos), booleans, None/null, containers vacios
- `_normalize_value()` — normaliza para comparacion: quita comillas, unifica True/true, None/null/undefined

**Decision:** Solo se detectan literals simples como valores de mock. Valores complejos (funciones, listas, dicts) se ignoran para evitar falsos positivos.

**Tests:** 18 tests en `test_analyzers/test_tests/test_mock_checker.py`

### F3.4 — TestQualityAnalyzer

**Archivo:** `src/vigil/analyzers/tests/analyzer.py`

- `TestQualityAnalyzer` — implementa `BaseAnalyzer` Protocol
  - `name = "test-quality"`, `category = Category.TEST_QUALITY`
  - `__test__ = False` — previene que pytest recolecte la clase como test
  - `analyze(files, config)` — itera archivos de test, extrae funciones, aplica reglas

**Reglas implementadas:**
- **TEST-001** (HIGH) — Test sin assertions (o con menos de `min_assertions_per_test`)
- **TEST-002** (MEDIUM) — Todas las assertions son triviales (solo reporta si 100% triviales)
- **TEST-003** (MEDIUM) — Catch-all exceptions (except Exception/BaseException + pass)
- **TEST-004** (LOW) — Skip sin justificacion (analisis global por archivo)
- **TEST-005** (MEDIUM) — Test de API sin verificacion de status code
- **TEST-006** (MEDIUM) — Mock mirror (mock retorna literal que coincide con assert)

**Flujo:**
1. Filtrar archivos de test (Python o JS/TS)
2. Leer contenido con `_read_file_safe()` (tolerante a encoding)
3. Detectar skips sin razon (TEST-004, global)
4. Extraer funciones de test
5. Para cada funcion: saltar si esta marcada como skip, luego aplicar TEST-001 a TEST-006

**Configuracion:** `TestQualityConfig` con:
- `min_assertions_per_test` (default 1) — threshold para TEST-001
- `detect_trivial_asserts` (default True) — habilita/deshabilita TEST-002
- `detect_mock_mirrors` (default True) — habilita/deshabilita TEST-006

**Tests:** 32 tests en `test_analyzers/test_tests/test_analyzer.py`

### F3.5 — Wiring al CLI

**Archivo modificado:** `src/vigil/cli.py`

- `_register_analyzers()` actualizado para registrar `TestQualityAnalyzer` ademas de `DependencyAnalyzer`, `AuthAnalyzer` y `SecretsAnalyzer`
- Los cuatro analyzers se ejecutan en `vigil scan` por defecto
- `vigil tests` ejecuta el scan filtrando por categoria `test-quality`

**Tests CLI actualizados:**
- `TestTestsCommand` en `test_cli_edge_cases.py` actualizado: test content cambiado de `assert True` a `assert 1 + 1 == 2` para evitar que TEST-002 se active con el analyzer real
- `test_tests_min_assertions` exit code actualizado de 0 a 1

### F3.Fixtures — Test fixtures

**Archivos creados en `tests/fixtures/tests/`:**

- `empty_tests_python.py` — Python tests con issues de todas las categorias (TEST-001 a TEST-006) + tests legitimos que NO deben triggear
- `empty_tests_js.js` — JavaScript tests con issues equivalentes + tests limpios
- `secure_tests_python.py` — Tests bien escritos (0 findings esperados)
- `edge_cases_python.py` — async tests, single-line tests, nested classes, parametrized, BaseException catches, mock mirrors, mixed assertions
- `edge_cases_js.js` — async tests, describe blocks, nested braces, catch-all, mock resolved mirrors, skips
- `npm_tests.test.js` — proyecto npm simulado con mix de tests buenos y malos

### Resumen de tests FASE 3

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_analyzers/test_tests/test_analyzer.py` | 32 | ~98% analyzer.py |
| `test_analyzers/test_tests/test_assert_checker.py` | 46 | ~99% assert_checker.py |
| `test_analyzers/test_tests/test_mock_checker.py` | 18 | ~96% mock_checker.py |
| `test_analyzers/test_tests/test_coverage_heuristics.py` | 20 | 100% coverage_heuristics.py |
| **Total FASE 3 (pre-QA)** | **116** | **~97%** |

### F3.QA — Auditoria de calidad y tests adicionales

**Estado: COMPLETADA**

Se realizo una auditoria exhaustiva del codigo de FASE 3. Se encontraron 6 bugs y se corrigieron todos.

**Bugs corregidos:**

1. **`assert_checker.py:14`** — `_PYTHON_TEST_FUNC` regex no matcheaba `async def test_*`. Agregado `(?:async\s+)?` al patron.
2. **`assert_checker.py:179-204`** — Funciones single-line `def test_x(): assert True` tenian 0 assertions porque el body empezaba en la linea siguiente. Agregada deteccion de inline body (`has_inline_body`) que incluye la linea del def en el range del body.
3. **`assert_checker.py:93-95`** — `_PYTHON_CATCH_ALL` no matcheaba `except BaseException:`. Agregado `(?:Base)?` al regex.
4. **`mock_checker.py:39-48`** — `_LITERAL_PATTERN` aceptaba comillas mixtas (`'hello"`) como literal valido. Separado en dos patrones: `'[^']*'` y `"[^"]*"`.
5. **`analyzer.py:316`** — `import re` dentro del cuerpo de `_is_skipped_test()`. Movido a import a nivel de modulo.
6. **`assert_checker.py:150-152`** — `_JS_STATUS_ASSERT` no matcheaba `toHaveProperty('status', ...)`. Agregado patron al regex.

**Limitaciones documentadas (no bugs):**

- Trivial detection no funciona en tests single-line inline (`def test_x(): assert True` — la assertion se cuenta pero el patron trivial no matchea la linea completa)
- `@patch("module.func", return_value=42)` decorator no matcheado por `_PYTHON_MOCK_PATCH_RETURN` (solo matchea `@mock.patch` / `@unittest.mock.patch`)
- Conteo de llaves en JS puede confundirse con llaves dentro de strings (limitacion conocida V0)
- Block comments (`/* */`, `"""`) no detectados como comentarios (limitacion compartida con auth/secrets)

**Tests nuevos: 81 tests en 1 archivo + fixtures en 3 archivos:**

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_analyzers/test_tests/test_qa_regression.py` | 81 | Regression bugs 1-4, edge cases (async, single-line, nested, binary, multifile), false positives (12), false negatives (7), configuration (5), fixture integration (5), boundary conditions (11), coverage heuristics (8), finding structure (7) |

**Fixtures nuevas en `tests/fixtures/tests/`:**

- `edge_cases_python.py` — async, single-line, nested classes, BaseException, parametrized, mock mirrors, mixed assertions
- `edge_cases_js.js` — async, describe wrapping, nested braces, catch-all, mock resolved, skips
- `npm_tests.test.js` — jest tests con mix de issues

**Cobertura por modulo post-QA:**

| Modulo | Stmts | Miss | Cobertura |
|--------|-------|------|-----------|
| `analyzers/tests/__init__.py` | 2 | 0 | 100% |
| `analyzers/tests/analyzer.py` | 86 | 2 | 98% |
| `analyzers/tests/assert_checker.py` | 149 | 2 | 99% |
| `analyzers/tests/coverage_heuristics.py` | 35 | 0 | 100% |
| `analyzers/tests/mock_checker.py` | 77 | 3 | 96% |
| **Total FASE 3** | **349** | **7** | **98%** |

**Totales post-QA FASE 3:**
- Tests FASE 3: 209 (128 originales + 81 QA)
- Tests totales proyecto: 1170
- Cobertura FASE 3: 98%

---

## FASE 4 — Reports + Formatters

**Estado: Parcialmente completada (base en FASE 0)**

Los 4 formatters (human, JSON, JUnit, SARIF) ya estan implementados funcionalmente. Pendiente:
- Polish del human formatter con findings reales
- Validacion de SARIF contra el schema oficial
- Mejoras de presentacion con findings de multiples categorias

---

## FASE 5 — Integration + Testing + Docs

**Estado: Pendiente**

Pendiente de implementar:
- F5.1 — Wiring de todos los analyzers al CLI
- F5.2 — Test suite con fixtures de codigo AI-generated real
- F5.3 — README final, documentacion de reglas

---

## FASE 6 — Data + Polish

**Estado: Pendiente**

Pendiente de implementar:
- F6.1 — Script para generar corpus de paquetes populares (top 5000 PyPI + npm)
- F6.2 — Polish final: exit codes, --quiet, --verbose, --offline, --changed-only
