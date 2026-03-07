# Configuracion

vigil se configura mediante un archivo YAML, flags de CLI, o una combinacion de ambos. La configuracion sigue un modelo de tres capas con merge progresivo.

## Orden de precedencia

```
Defaults (codigo) < Archivo YAML (.vigil.yaml) < Flags del CLI
```

Los flags del CLI siempre tienen la prioridad mas alta. Esto permite tener un archivo de configuracion base para el equipo y hacer ajustes puntuales por ejecucion.

## Archivo de configuracion

### Creacion

```bash
# Generar con defaults
vigil init

# Generar con estrategia estricta
vigil init --strategy strict

# Generar en un directorio especifico
vigil init /ruta/al/proyecto
```

### Nombres soportados

vigil busca automaticamente estos archivos, en este orden:

1. `.vigil.yaml`
2. `.vigil.yml`
3. `vigil.yaml`
4. `vigil.yml`

La busqueda comienza en el directorio actual y sube por el arbol de directorios hasta la raiz. Esto permite tener un archivo de configuracion en la raiz del monorepo que aplique a todos los subproyectos.

### Especificar ruta explicita

```bash
vigil scan src/ --config /ruta/a/mi-config.yaml
```

---

## Referencia completa

### Configuracion general

```yaml
# Directorios a incluir en el scan
include:
  - "src/"
  - "lib/"
  - "app/"

# Directorios y patrones a excluir
exclude:
  - "node_modules/"
  - ".venv/"
  - "__pycache__/"
  - ".git/"
  - "dist/"
  - "build/"
  - ".tox/"
  - ".mypy_cache/"

# Directorios de tests (usados por el subcomando `vigil tests`)
test_dirs:
  - "tests/"
  - "test/"
  - "__tests__/"

# Severidad minima para fallar con exit code 1
# Opciones: critical, high, medium, low
fail_on: "high"

# Lenguajes a escanear
# Opciones: python, javascript
languages:
  - python
  - javascript
```

### Dependencias (`deps`)

Configuracion del analyzer de dependencias (CAT-01).

```yaml
deps:
  # Verificar existencia de paquetes en PyPI/npm via HTTP
  verify_registry: true

  # Minimo de dias de antiguedad para considerar un paquete seguro
  # Paquetes mas nuevos que esto generan DEP-002
  min_age_days: 30

  # Minimo de descargas semanales para considerar un paquete seguro
  # Paquetes con menos descargas generan DEP-004
  min_weekly_downloads: 100

  # Umbral de similitud para deteccion de typosquatting (0.0 a 1.0)
  # Valores mas altos = menos falsos positivos, mas falsos negativos
  # 0.85 es un buen balance
  similarity_threshold: 0.85

  # Tiempo de vida del cache de respuestas del registry (en horas)
  # Evita hacer la misma request HTTP dos veces en 24 horas
  cache_ttl_hours: 24

  # Modo offline: no hacer ninguna request HTTP
  # Solo ejecuta checks estaticos (similaridad, imports sin declarar)
  offline_mode: false

  # Ruta a un archivo personalizado de paquetes populares (JSON)
  # Por defecto usa el corpus bundled en data/
  # popular_packages_file: "/ruta/a/mis-paquetes.json"
```

### Autenticacion (`auth`)

Configuracion del analyzer de patrones de autenticacion (CAT-02).

```yaml
auth:
  # Maximo de horas de lifetime para un JWT
  # Tokens con lifetime mayor generan AUTH-003
  max_token_lifetime_hours: 24

  # Requerir autenticacion en endpoints mutantes (PUT, DELETE, PATCH)
  # Si es true, endpoints mutantes sin auth middleware generan AUTH-002
  require_auth_on_mutating: true

  # Permitir CORS con localhost en modo desarrollo
  # Si es true, `cors(origin: 'http://localhost:*')` no genera AUTH-005
  cors_allow_localhost: true
```

### Secrets (`secrets`)

Configuracion del analyzer de secrets y credenciales (CAT-03).

```yaml
secrets:
  # Entropia minima de Shannon (bits/caracter) para considerar un string como secret
  # Valores tipicos: < 3.0 = placeholder, > 4.5 = secret real
  min_entropy: 3.0

  # Comparar valores en codigo con los de .env.example
  # Si un valor en codigo coincide con uno de .env.example, genera SEC-006
  check_env_example: true

  # Patrones regex de placeholders conocidos
  # Si un valor asignado a una variable sensible coincide con estos patrones, genera SEC-001
  # El default incluye 30 patrones (ver schema.py para la lista completa)
  placeholder_patterns:
    - "changeme"
    - "your[-_].*[-_]here"
    - "replace[-_]?me"
    - "insert[-_].*[-_]here"
    - "put[-_].*[-_]here"
    - "add[-_].*[-_]here"
    - "TODO"
    - "FIXME"
    - "xxx+"
    - "sk[-_]your.*"
    - "pk[-_]test[-_].*"
    - "sk[-_]test[-_].*"
    - "sk[-_]live[-_]test.*"
    - "secret123"
    - "password123"
    - "supersecret"
    - "mysecret"
    - "my[-_]?secret[-_]?key"
    - "example\\.com"
    - "test[-_]?key"
    - "test[-_]?secret"
    - "dummy[-_]?key"
    - "dummy[-_]?secret"
    - "fake[-_]?key"
    - "fake[-_]?secret"
    - "sample[-_]?key"
    - "sample[-_]?secret"
    - "default[-_]?secret"
    - "default[-_]?key"
    - "placeholder"
```

### Test quality (`tests`)

Configuracion del analyzer de calidad de tests (CAT-06).

```yaml
tests:
  # Minimo de assertions requeridas por funcion de test
  # Tests con menos assertions generan TEST-001
  min_assertions_per_test: 1

  # Detectar assertions triviales (assert True, assert x is not None)
  detect_trivial_asserts: true

  # Detectar mocks que replican exactamente la implementacion
  detect_mock_mirrors: true
```

### Output

```yaml
output:
  # Formato de salida: human, json, junit, sarif
  format: "human"

  # Archivo de salida (null = stdout)
  output_file: null

  # Usar colores ANSI en la terminal
  colors: true

  # Output detallado
  verbose: false

  # Mostrar sugerencias de correccion
  show_suggestions: true
```

---

## Rule overrides

Puedes deshabilitar reglas individuales o cambiar su severidad.

```yaml
rules:
  # Deshabilitar una regla completamente
  AUTH-003:
    enabled: false

  # Cambiar la severidad de una regla
  DEP-004:
    severity: "low"

  # Combinar: habilitar con severidad diferente
  TEST-002:
    enabled: true
    severity: "high"
```

### Overrides comunes

```yaml
rules:
  # Si tu proyecto usa tokens de larga duracion intencionalmente
  AUTH-003:
    enabled: false

  # Si tienes dependencias internas con pocas descargas
  DEP-004:
    severity: "low"

  # Si permites CORS abierto en desarrollo
  AUTH-005:
    severity: "medium"

  # Si tus tests usan un framework custom sin assertions estandar
  TEST-001:
    enabled: false
```

---

## Estrategias predefinidas

### `strict`

Para entornos con requisitos de compliance altos (SOC 2, ISO 27001, EU CRA).

```yaml
fail_on: "medium"
deps:
  min_age_days: 60
  min_weekly_downloads: 500
auth:
  max_token_lifetime_hours: 1
```

### `standard` (default)

Para la mayoria de proyectos. Balance entre seguridad y practicidad.

```yaml
fail_on: "high"
deps:
  min_age_days: 30
  min_weekly_downloads: 100
auth:
  max_token_lifetime_hours: 24
```

### `relaxed`

Para prototipos, pruebas de concepto, o proyectos en fase temprana.

```yaml
fail_on: "critical"
deps:
  min_age_days: 7
  min_weekly_downloads: 10
auth:
  max_token_lifetime_hours: 72
```

---

## Configuracion por entorno

Una practica comun es tener multiples archivos de configuracion:

```
proyecto/
  .vigil.yaml            # Config base del equipo (commiteada)
  .vigil.strict.yaml     # Config para produccion
  .vigil.dev.yaml        # Config para desarrollo local
```

```bash
# Desarrollo local
vigil scan src/

# Pipeline de CI para produccion
vigil scan src/ --config .vigil.strict.yaml
```

---

## Variables de entorno

vigil no lee variables de entorno directamente para su configuracion. Toda la configuracion se hace via YAML o CLI flags. Esto es intencional para mantener la herramienta determinista y evitar comportamientos inesperados.

Si necesitas configuracion dinamica, puedes generar el archivo YAML como parte de tu pipeline:

```bash
# Ejemplo: generar config dinamicamente segun el entorno
if [ "$CI" = "true" ]; then
    vigil scan src/ --config .vigil.strict.yaml --fail-on medium
else
    vigil scan src/ --fail-on high
fi
```

---

## Cache

vigil almacena cache de las respuestas de registries (PyPI/npm) en:

```
~/.cache/vigil/registry/
```

- El TTL por defecto es 24 horas (configurable con `deps.cache_ttl_hours`).
- Cada paquete se cachea individualmente como un archivo JSON.
- El cache se comparte entre ejecuciones para evitar requests repetidas.

### Limpiar el cache

```bash
rm -rf ~/.cache/vigil/registry/
```

### Deshabilitar el cache

No hay una opcion explicita para deshabilitarlo. Puedes usar `cache_ttl_hours: 0` para forzar requests frescas en cada ejecucion, o `--offline` para no hacer requests en absoluto.
