# Analizadores

vigil usa un sistema de analyzers modulares. Cada analyzer se enfoca en una categoria de deteccion y produce findings independientemente. Este documento describe los analyzers implementados.

Para la arquitectura general de los analyzers (protocolo, registro, flujo), ver [arquitectura.md](arquitectura.md).

---

## DependencyAnalyzer (CAT-01)

**Modulo:** `src/vigil/analyzers/deps/`
**Categoria:** `dependency`
**Reglas activas:** DEP-001, DEP-002, DEP-003, DEP-005, DEP-007

Detecta dependencias alucinadas (slopsquatting), typosquatting, paquetes sospechosos, versiones inexistentes y paquetes sin repositorio fuente.

### Archivos de dependencias soportados

| Archivo | Ecosistema | Parser |
|---------|------------|--------|
| `requirements.txt` | PyPI | `parse_requirements_txt()` |
| `requirements-dev.txt`, `requirements-*.txt` | PyPI | `parse_requirements_txt()` |
| `pyproject.toml` (`[project.dependencies]`, `[project.optional-dependencies]`) | PyPI | `parse_pyproject_toml()` |
| `package.json` (`dependencies`, `devDependencies`) | npm | `parse_package_json()` |

Los archivos se descubren automaticamente con `find_and_parse_all()`, que recorre el arbol de directorios evitando `.venv/`, `node_modules/`, `.git/`, etc.

### Reglas implementadas

#### DEP-001 — Hallucinated dependency (CRITICAL)

Verifica que cada paquete declarado exista en el registry publico (PyPI o npm). Si no existe, es muy probable que sea un nombre alucinado por el agente de IA.

```
# requirements.txt
flask==3.0.0
python-jwt-utils==1.0.0    # NO existe en PyPI -> DEP-001 CRITICAL
```

**Requiere red:** Si. Se omite en modo `--offline`.

#### DEP-002 — Suspiciously new dependency (HIGH)

Verifica la fecha de creacion del paquete. Si fue creado hace menos de `deps.min_age_days` dias (default: 30), puede ser un paquete malicioso registrado como parte de un ataque de slopsquatting.

**Requiere red:** Si. Se omite en modo `--offline`.

#### DEP-003 — Typosquatting candidate (HIGH)

Compara el nombre de cada dependencia contra un corpus de paquetes populares usando distancia de Levenshtein normalizada. Si la similaridad es >= `deps.similarity_threshold` (default: 0.85), es un candidato a typosquatting.

```
# requirements.txt
requets==2.31.0     # Similaridad 0.875 con "requests" -> DEP-003 HIGH
```

**Requiere red:** No. Funciona en modo `--offline`.

**Normalizacion:** Para PyPI, hyphens (`-`), underscores (`_`) y dots (`.`) se tratan como equivalentes (PEP 503). `my-package`, `my_package` y `my.package` se normalizan al mismo nombre antes de comparar.

**Corpus:** Se usa un corpus built-in de ~100 paquetes PyPI y ~70 paquetes npm como fallback. Cuando se generen los archivos `data/popular_pypi.json` y `data/popular_npm.json` (FASE 6), se usaran esos.

#### DEP-005 — No source repository (MEDIUM)

Verifica que el paquete tenga un repositorio de codigo fuente vinculado en su metadata. Los paquetes sin repositorio son mas dificiles de auditar.

**Requiere red:** Si. Se omite en modo `--offline`.

#### DEP-007 — Nonexistent version (CRITICAL)

Verifica que la version exacta especificada (pinned) exista en el registry. Solo aplica a versiones exactas (`==1.2.3` en PyPI, `1.2.3` sin prefijo en npm).

```
# requirements.txt
flask==99.0.0     # Version no existe -> DEP-007 CRITICAL
```

**Requiere red:** Si. Se omite en modo `--offline`.

### Reglas diferidas

| Regla | Razon | Estimacion |
|-------|-------|------------|
| DEP-004 (unpopular) | Requiere API de estadisticas de descargas, no disponible en la metadata basica de PyPI/npm | V1 o FASE 6 |
| DEP-006 (missing import) | Requiere parser de imports AST, fuera de scope V0 (regex-based) | V1 |

### Flujo de analisis

1. **Descubrimiento**: `find_and_parse_all()` recorre los directorios con `os.walk()` + pruning, buscando archivos de dependencias.
2. **Parsing**: Cada archivo se parsea en una lista de `DeclaredDependency` con nombre, version, archivo fuente, linea y ecosistema.
3. **Deduplicacion**: Se eliminan duplicados por nombre+ecosistema (ej: mismo paquete en `requirements.txt` y `pyproject.toml`).
4. **Verificacion de registry** (si online): Para cada paquete unico, se consulta PyPI/npm via `RegistryClient`. Se aplican DEP-001, DEP-002, DEP-005, DEP-007.
5. **Verificacion de similaridad** (siempre): Para cada paquete unico, se buscan paquetes populares con nombres similares. Se aplica DEP-003.

### Registry Client

El `RegistryClient` maneja las consultas HTTP a PyPI y npm:

- **Cache en disco:** `~/.cache/vigil/registry/` con archivos JSON individuales por paquete.
- **TTL configurable:** Default 24 horas (`deps.cache_ttl_hours`).
- **Lazy init:** El cliente httpx se crea solo cuando se hace la primera request.
- **Context manager:** Soporta `with RegistryClient() as client:` para cleanup automatico.
- **Resiliencia:** Los errores de red asumen que el paquete existe (evita falsos positivos en conexiones inestables).

```bash
# Limpiar cache
rm -rf ~/.cache/vigil/registry/

# Forzar requests frescas
# (configurar cache_ttl_hours: 0 en .vigil.yaml)
```

### Configuracion relevante

```yaml
deps:
  # Verificar contra registries (false = solo checks estaticos)
  verify_registry: true

  # Dias minimos de antiguedad (DEP-002)
  min_age_days: 30

  # Umbral de similaridad para typosquatting (DEP-003)
  # 0.85 = captura typos de 1 caracter en nombres de 8+ caracteres
  similarity_threshold: 0.85

  # TTL del cache de registry
  cache_ttl_hours: 24

  # Modo offline (no HTTP)
  offline_mode: false
```

### Modo offline

Con `--offline` o `deps.offline_mode: true`:

| Regla | Comportamiento |
|-------|---------------|
| DEP-001 | **Omitida** (requiere verificar registry) |
| DEP-002 | **Omitida** (requiere fecha de creacion del registry) |
| DEP-003 | **Activa** (comparacion local contra corpus) |
| DEP-005 | **Omitida** (requiere metadata del registry) |
| DEP-007 | **Omitida** (requiere lista de versiones del registry) |

---

## Analyzers pendientes

### AuthAnalyzer (CAT-02) — FASE 2

Detectara patrones de autenticacion inseguros en FastAPI, Flask y Express mediante regex:
- Endpoints sin auth middleware (AUTH-001, AUTH-002)
- CORS con `*` (AUTH-005)
- JWT con secrets hardcodeados (AUTH-004)
- Cookies sin flags de seguridad (AUTH-006)
- Comparacion de passwords no timing-safe (AUTH-007)

### SecretsAnalyzer (CAT-03) — FASE 2

Detectara secrets y credenciales en codigo:
- Placeholders copiados de docs/ejemplos (SEC-001)
- Secrets con entropia baja (SEC-002)
- Connection strings con credenciales (SEC-003)
- Variables de entorno con defaults sensibles (SEC-004)
- Archivos de secrets fuera de .gitignore (SEC-005)
- Valores copiados de .env.example (SEC-006)

### TestQualityAnalyzer (CAT-06) — FASE 3

Detectara tests que dan cobertura falsa:
- Tests sin assertions (TEST-001)
- Assertions triviales (TEST-002)
- Captura generica de excepciones en tests (TEST-003)
- Tests skipped sin razon (TEST-004)
- Tests de API sin verificar status code (TEST-005)
- Mocks que replican la implementacion (TEST-006)
