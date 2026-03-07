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

## AuthAnalyzer (CAT-02)

**Modulo:** `src/vigil/analyzers/auth/`
**Categoria:** `auth`
**Reglas activas:** AUTH-001, AUTH-002, AUTH-003, AUTH-004, AUTH-005, AUTH-006, AUTH-007

Detecta patrones de autenticacion y autorizacion inseguros en Python (FastAPI/Flask) y JavaScript (Express) mediante pattern matching con regex.

### Arquitectura interna

El analyzer se compone de 4 modulos:

| Modulo | Responsabilidad |
|--------|----------------|
| `analyzer.py` | Orquesta la deteccion, itera archivos y lineas |
| `endpoint_detector.py` | Detecta endpoints HTTP (decorators en Python, `app.get/post/...` en JS) |
| `middleware_checker.py` | Verifica si un endpoint tiene middleware de auth (`Depends(...)`, `passport`, etc.) |
| `patterns.py` | Patrones regex para JWT lifetime, secrets hardcodeados, CORS, cookies, passwords |

```
AuthAnalyzer.analyze(files, config)
    |
    v
[1. Filtrar archivos relevantes (.py, .js, .ts, .jsx, .tsx)]
    |
    v
[2. detect_endpoints(content)]  -->  Lista de EndpointInfo
    |                                 (ruta, metodo, linea, framework)
    v
[3. check_endpoint_auth(ep)]  -->  AUTH-001 / AUTH-002 findings
    |
    v
[4. _check_lines() por linea]
    +---> AUTH-003: JWT lifetime excesivo
    +---> AUTH-004: Secret hardcodeado con baja entropy
    +---> AUTH-005: CORS allow all origins
    +---> AUTH-006: Cookie sin flags de seguridad
    +---> AUTH-007: Password comparison no timing-safe
    |
    v
  list[Finding]
```

### Reglas implementadas

| Regla | Severidad | Requiere red | Descripcion |
|-------|-----------|-------------|-------------|
| AUTH-001 | HIGH | No | Endpoint sensible sin auth middleware |
| AUTH-002 | HIGH | No | Endpoint mutante (DELETE/PUT/PATCH) sin auth |
| AUTH-003 | MEDIUM | No | JWT con lifetime excesivo (>24h por defecto) |
| AUTH-004 | CRITICAL | No | JWT secret hardcodeado con baja entropy |
| AUTH-005 | HIGH | No | CORS configurado con `*` (allow all) |
| AUTH-006 | MEDIUM | No | Cookie sin flags de seguridad (httpOnly, secure, sameSite) |
| AUTH-007 | MEDIUM | No | Comparacion de passwords con `==` (vulnerable a timing attacks) |

Todas las reglas son offline — no requieren red. Solo analizan codigo fuente.

### Deteccion de endpoints

El `endpoint_detector` detecta endpoints HTTP en tres frameworks:

**FastAPI/Flask (Python):**
```python
@app.get("/users/{user_id}")        # Detectado
@router.delete("/users/{user_id}")  # Detectado
@app.route("/admin", methods=["POST"])  # Detectado
```

**Express (JavaScript):**
```javascript
app.get("/users/:id", handler)       // Detectado
router.delete("/users/:id", handler) // Detectado
```

La deteccion de auth middleware busca:
- Python: `Depends(...)`, `login_required`, `@requires_auth`, `Permission`, `current_user`
- JavaScript: `passport`, `authenticate`, `isAuthenticated`, `requireAuth`, `authMiddleware`

### Heuristicas de endpoints sensibles (AUTH-001)

Un endpoint se considera sensible si su ruta contiene tokens como:
`user`, `admin`, `account`, `profile`, `payment`, `order`, `billing`, `settings`, `password`, `token`, `auth`, `session`, `dashboard`

### Configuracion relevante

```yaml
auth:
  # Maximo horas de lifetime para JWT (AUTH-003)
  max_token_lifetime_hours: 24

  # Requerir auth en endpoints mutantes (AUTH-002)
  require_auth_on_mutating: true

  # Permitir CORS abierto en archivos de dev/test (AUTH-005)
  cors_allow_localhost: true
```

### Integracion con SecretsAnalyzer

AUTH-004 (hardcoded JWT secret) usa `shannon_entropy()` del modulo `secrets/entropy.py` para calcular la entropia del valor. Solo reporta secrets con entropia < 4.0 bits/char (placeholders tipicos como `"supersecret"` o `"secret123"`). Los secrets con alta entropia se dejan para SEC-002.

---

## SecretsAnalyzer (CAT-03)

**Modulo:** `src/vigil/analyzers/secrets/`
**Categoria:** `secrets`
**Reglas activas:** SEC-001, SEC-002, SEC-003, SEC-004, SEC-006

Detecta secrets y credenciales mal gestionados en codigo, con enfasis en patrones tipicos de codigo generado por IA: placeholders copiados, secrets de baja entropia, y valores de `.env.example` embebidos.

### Arquitectura interna

| Modulo | Responsabilidad |
|--------|----------------|
| `analyzer.py` | Orquesta la deteccion, aplica checks por linea y por archivo |
| `placeholder_detector.py` | Compila regex de placeholders, detecta assignments de secrets |
| `entropy.py` | Calcula Shannon entropy para distinguir secrets reales de placeholders |
| `env_tracer.py` | Parsea `.env.example`, busca valores copiados en codigo fuente |

```
SecretsAnalyzer.analyze(files, config)
    |
    v
[1. Compilar placeholder_patterns (30 regex)]
    |
    v
[2. Cargar .env.example entries (si check_env_example=true)]
    |
    v
[3. Por cada archivo relevante (.py, .js, .ts, ...)]
    +---> SEC-006: find_env_values_in_code() contra entries de .env.example
    +---> SEC-003: Connection strings con credenciales (postgresql://, mongodb://, etc.)
    +---> SEC-004: Env vars sensibles con default hardcodeado
    +---> SEC-001: Secret assignment con valor placeholder
    +---> SEC-002: Secret assignment con baja entropy
    |
    v
  list[Finding]
```

### Reglas implementadas

| Regla | Severidad | Descripcion |
|-------|-----------|-------------|
| SEC-001 | CRITICAL | Valor placeholder en codigo (`"your-api-key-here"`, `"changeme"`, etc.) |
| SEC-002 | CRITICAL | Secret hardcodeado con baja entropy (< 3.0 bits/char por defecto) |
| SEC-003 | CRITICAL | Connection string con credenciales embebidas (postgresql://, mongodb://, etc.) |
| SEC-004 | HIGH | Variable de entorno sensible con valor default en codigo |
| SEC-006 | CRITICAL | Valor copiado textualmente de `.env.example` al codigo fuente |

### Regla diferida

| Regla | Razon | Estimacion |
|-------|-------|------------|
| SEC-005 (file not in gitignore) | Requiere analisis de `.gitignore` con patrones glob | V1 o FASE posterior |

### Deteccion de placeholders (SEC-001)

El analyzer viene con **30 patrones regex** de placeholders conocidos, configurables via `secrets.placeholder_patterns`:

- Valores genericos: `changeme`, `TODO`, `FIXME`, `placeholder`, `xxx+`
- Patrones con template: `your-*-here`, `replace-me`, `insert-*-here`, `put-*-here`, `add-*-here`
- Prefijos de API keys: `sk-your*`, `pk_test_*`, `sk_test_*`, `sk_live_test*`
- Valores tipicos de AI: `secret123`, `password123`, `supersecret`, `mysecret`, `my-secret-key`
- Valores de ejemplo: `example.com`, `test-key`, `dummy-key`, `fake-key`, `sample-key`, `default-secret`

### Shannon entropy (SEC-002)

La deteccion de secrets de baja entropia usa el calculo de Shannon entropy:

- `"password123"` → ~2.8 bits/char (placeholder)
- `"xK8$mP2!qR"` → ~3.3 bits/char (borderline)
- `"a1b2c3d4e5f6g7h8"` → ~4.0 bits/char (probablemente real)

El threshold por defecto es 3.0 bits/char. Se configura con `secrets.min_entropy`.

### Deteccion de connection strings (SEC-003)

Protocolos soportados: `postgresql`, `postgres`, `mysql`, `mariadb`, `mongodb`, `mongodb+srv`, `redis`, `amqp`, `rabbitmq`, `sqlserver`, `mssql`.

```python
# Detectado
DATABASE_URL = "postgresql://admin:password123@db.example.com:5432/mydb"

# NO detectado (usa variable de entorno en el password)
DATABASE_URL = f"postgresql://admin:${DB_PASS}@db.example.com:5432/mydb"
```

En los snippets de output, el password se redacta automaticamente: `postgresql://admin:***@db.example.com:5432/mydb`.

### Deteccion de env defaults (SEC-004)

Detecta variables de entorno sensibles con valores por defecto hardcodeados:

```python
# Python — detectado
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
API_KEY = os.environ.get("API_KEY", "test-key-123")

# JavaScript — detectado
const secret = process.env.SECRET_KEY || "mysecret"
const key = process.env["API_KEY"] || "default-key"
```

Solo reporta si el nombre de la variable contiene tokens sensibles: `SECRET`, `KEY`, `TOKEN`, `PASSWORD`, `API_KEY`, `AUTH`, `JWT`, `DATABASE_URL`, `DB_PASS`, `PRIVATE_KEY`, `ENCRYPTION`, `SIGNING`, `STRIPE`, `AWS`.

### Tracing de .env.example (SEC-006)

Si `secrets.check_env_example: true` (default), el analyzer:

1. Busca archivos `.env.example`, `.env.sample`, `.env.template` en los directorios raiz.
2. Parsea cada archivo extrayendo pares `KEY=value`.
3. Busca esos valores exactos en el codigo fuente.
4. Si un valor de `.env.example` aparece en un `.py` o `.js`, genera SEC-006 CRITICAL.

### Configuracion relevante

```yaml
secrets:
  # Entropia minima de Shannon para SEC-002
  min_entropy: 3.0

  # Comparar con .env.example para SEC-006
  check_env_example: true

  # Patrones regex de placeholders para SEC-001
  # (lista de 30 patrones por defecto — ver schema.py)
  placeholder_patterns:
    - "changeme"
    - "your-.*-here"
    - "replace-?me"
    # ... (30 patrones por defecto)
```

---

## Analyzer pendiente

### TestQualityAnalyzer (CAT-06) — FASE 3

Detectara tests que dan cobertura falsa:
- Tests sin assertions (TEST-001)
- Assertions triviales (TEST-002)
- Captura generica de excepciones en tests (TEST-003)
- Tests skipped sin razon (TEST-004)
- Tests de API sin verificar status code (TEST-005)
- Mocks que replican la implementacion (TEST-006)
