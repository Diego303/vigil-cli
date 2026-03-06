# Seguimiento de Implementacion V0 — vigil

> Documento de seguimiento detallado del progreso de implementacion del MVP de vigil.
> Cada fase se actualiza conforme se completa.

---

## Estado General

| Fase | Nombre | Estado | Tests |
|------|--------|--------|-------|
| FASE 0 | Scaffolding + Config + Core | COMPLETADA (QA done) | 350 |
| FASE 1 | Dependency Analyzer | Pendiente | — |
| FASE 2 | Auth & Secrets Analyzers | Pendiente | — |
| FASE 3 | Test Quality Analyzer | Pendiente | — |
| FASE 4 | Reports + Formatters | Pendiente | — |
| FASE 5 | Integration + Testing + Docs | Pendiente | — |
| FASE 6 | Data + Polish | Pendiente | — |

**Metricas actuales:**
- Tests totales: 350 (todos pasando, 0 warnings)
- Cobertura: 93% (671 statements, 49 missed)
- Archivos fuente: 23
- Archivos de test: 19

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

**Estado: Pendiente**

Pendiente de implementar:
- F1.1 — Parsers de dependencias (requirements.txt, pyproject.toml, package.json)
- F1.2 — Registry Client (PyPI + npm + cache local)
- F1.3 — Similarity checker (Levenshtein + corpus de paquetes populares)
- F1.4 — DependencyAnalyzer completo (DEP-001 a DEP-007)

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
