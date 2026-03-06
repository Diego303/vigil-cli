# Seguimiento de Implementacion V0 — vigil

> Documento de seguimiento detallado del progreso de implementacion del MVP de vigil.
> Cada fase se actualiza conforme se completa.

---

## Estado General

| Fase | Nombre | Estado | Tests |
|------|--------|--------|-------|
| FASE 0 | Scaffolding + Config + Core | COMPLETADA (QA done) | 350 |
| FASE 1 | Dependency Analyzer | COMPLETADA (QA done) | 282 |
| FASE 2 | Auth & Secrets Analyzers | Pendiente | — |
| FASE 3 | Test Quality Analyzer | Pendiente | — |
| FASE 4 | Reports + Formatters | Pendiente | — |
| FASE 5 | Integration + Testing + Docs | Pendiente | — |
| FASE 6 | Data + Polish | Pendiente | — |

**Metricas actuales:**
- Tests totales: 632 (todos pasando, 0 warnings)
- Cobertura: ~94%
- Archivos fuente: 27
- Archivos de test: 28

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

**Estado: Pendiente**

Pendiente de implementar:
- F2.1 — AuthAnalyzer (FastAPI, Flask, Express patterns via regex)
- F2.2 — SecretsAnalyzer (placeholders, entropy, env tracer, connection strings)

---

## FASE 3 — Test Quality Analyzer

**Estado: Pendiente**

Pendiente de implementar:
- F3.1 — TestQualityAnalyzer (pytest, jest/mocha)
- F3.2 — Assert checker, mock mirror detection

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
