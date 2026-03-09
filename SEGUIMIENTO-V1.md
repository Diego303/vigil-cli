# Seguimiento de Implementacion V1 — vigil

> Documento de seguimiento activo a partir de v1.0.0.
> Para historial detallado de V0 (fases 0-6 + QA), ver `SEGUIMIENTO-V0.md`.

---

## Estado Actual

**Version:** v1.0.0 (stable release)

| Metrica | Valor |
|---------|-------|
| Tests | 1706 (todos pasando) |
| Cobertura | 97% (2175 statements, 64 missed) |
| Archivos fuente | 43 (~5.900 LOC) |
| Archivos de test | 76 (~20.300 LOC) |
| Reglas implementadas | 24 de 26 |
| Analizadores | 4 (dependency, auth, secrets, test_quality) |
| Formatos de salida | 4 (human, json, junit, sarif) |

### Reglas no implementadas

| Regla | Motivo |
|-------|--------|
| DEP-004 (unpopular package) | Requiere API de estadisticas de descargas; diferido |
| DEP-006 (undeclared import) | Requiere parsing de imports vs dependencias declaradas; diferido |

### Limitaciones conocidas de V0/V1

- Deteccion basada en regex, no AST (AST es scope futuro)
- Block comments (`/* */`, `"""`) no detectados como comentarios
- SEC-005 (file not in .gitignore) no implementado — requiere parsing de .gitignore
- `_read_file_safe` duplicada en auth, secrets y tests analyzers (candidato a refactor)
- `include` en config existe pero no se usa en `collect_files`
- Login endpoints (POST /login) disparan AUTH-002 por diseno (desactivable via config)

---

## Arquitectura

```
src/vigil/
  cli.py                   # Click CLI (main, scan, deps, tests, init, rules)
  config/
    schema.py              # Pydantic v2 (ScanConfig, DepsConfig, AuthConfig, etc.)
    loader.py              # YAML + CLI merge + strategy presets
    rules.py               # RULES_V0 catalog (26 definiciones)
  core/
    finding.py             # Finding, Severity, Category, Location
    engine.py              # ScanEngine orchestrator + ScanResult
    file_collector.py      # File discovery con filtros de lenguaje/exclusion
    rule_registry.py       # RuleRegistry con filtros
  analyzers/
    base.py                # BaseAnalyzer Protocol
    deps/                  # CAT-01: DEP-001..007 (parsers, registry_client, similarity)
    auth/                  # CAT-02: AUTH-001..007 (endpoint_detector, middleware_checker)
    secrets/               # CAT-03: SEC-001..006 (entropy, placeholder_detector, env_tracer)
    tests/                 # CAT-06: TEST-001..006 (assert_checker, mock_checker)
  reports/
    human.py, json_fmt.py, junit.py, sarif.py, summary.py
  logging/setup.py         # structlog (stderr)
data/
  popular_pypi.json        # 5000 paquetes PyPI
  popular_npm.json         # 3454 paquetes npm
  placeholder_patterns.json
```

**Flujo:** CLI → ScanEngine → collect files → run analyzers → apply overrides → sort → format output

**Precedencia de config:** defaults ← `.vigil.yaml` ← CLI flags

**Exit codes:** 0 = clean, 1 = findings, 2 = error

---

## Resumen de lo implementado en V0 → V1.0.0

### FASE 0 — Scaffolding + Config + Core (350 tests)
Proyecto base: CLI con Click, modelos Pydantic, ScanEngine, FileCollector, RuleRegistry, 4 formatters vacios, catalogo de 26 reglas.

### FASE 1 — Dependency Analyzer (282 tests)
Parsers (requirements.txt, pyproject.toml, package.json), RegistryClient (PyPI + npm con cache), similaridad Damerau-Levenshtein, corpus de paquetes populares. Reglas: DEP-001, DEP-002, DEP-003, DEP-005, DEP-007.

### FASE 2 — Auth & Secrets Analyzers (329 tests)
AuthAnalyzer: deteccion de endpoints (FastAPI/Flask/Express), middleware checker, patrones regex para JWT, CORS, cookies, passwords. SecretsAnalyzer: entropia Shannon, placeholder detector, env tracer. Reglas: AUTH-001..007, SEC-001..004, SEC-006.

### FASE 3 — Test Quality Analyzer (209 tests)
Extraccion de funciones test (Python/JS), conteo de asserts, deteccion trivial, skip detection, API test detection, mock mirror detection. Reglas: TEST-001..006.

### FASE 4 — Reports + Formatters (166 tests)
Polish de HumanFormatter (quiet mode, colors, Unicode icons), JsonFormatter (summary section), JunitFormatter (properties, categories), SarifFormatter (PascalCase, helpUri, ruleIndex, OWASP properties, invocations).

### FASE 5 — Integration + Testing (182 tests)
E2E tests con fixtures realistas (insecure_project + clean_project), CLI wiring completo, `--changed-only` con `git status -z`, tests de `python -m vigil`.

### FASE 6 — Data + Polish (188 tests)
Script de fetch de paquetes populares (5000 PyPI + 3454 npm), data/ JSON files, tests exhaustivos de todos los flags CLI, exit codes, interacciones de flags.

### V1 QA — Test exhaustivo + Bug fixes
164 pruebas manuales en 18 fases. 10 bugs corregidos:
- BUG-001: Damerau-Levenshtein para typosquatting por transposicion
- BUG-002: `vigil tests --offline` habilitado
- BUG-003: CORS dev-path heuristic usa segment matching exacto
- BUG-006: AWS example keys (AKIA...) detectadas como placeholder
- BUG-007: Path inexistente → exit code 2
- BUG-008: Redis connection strings (`redis://:pass@host`) detectadas
- BUG-009: YAML invalido → error claro + exit 2
- BUG-012: `--rule` CLI tiene prioridad sobre `enabled: false`
- BUG-013: Performance similaridad mejorada 3.4x
- Reportes: `VIGIL-V1-TEST-REPORT.md`, `VIGIL-V1-FIX-REPORT.md`

---

## Backlog V1+

> Items pendientes para futuras iteraciones.

- [ ] AST parsing (reemplazar regex donde sea posible)
- [ ] DEP-004: deteccion de paquetes con pocas descargas
- [ ] DEP-006: imports no declarados en dependencias
- [ ] SEC-005: archivos sensibles no listados en .gitignore
- [ ] Refactor: extraer `_read_file_safe` a utilidad comun
- [ ] Soporte para mas lenguajes (Go, Rust, Java)
- [ ] `vigil fix` — modo de auto-correccion
- [ ] Plugin system para reglas custom
- [ ] Watch mode (`vigil scan --watch`)
