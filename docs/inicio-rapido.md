# Inicio rapido

## Requisitos previos

- Python 3.12 o superior
- pip (incluido con Python)
- git (opcional, necesario para `--changed-only`)

## Instalacion

### Desde PyPI

```bash
pip install vigil-ai-cli
```

### Desde el codigo fuente (desarrollo)

```bash
git clone https://github.com/org/vigil.git
cd vigil
python3.12 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
pip install -e ".[dev]"
```

### Verificar la instalacion

```bash
vigil --version
# vigil, version 1.0.0
```

## Primer scan

Ejecuta vigil sobre el directorio de tu proyecto:

```bash
vigil scan src/
```

Ejemplo de salida cuando no hay problemas:

```
  vigil v1.0.0 — scanned 42 files

  No findings.

  -------------------------------------------------
  42 files scanned in 0.5s
  0 findings
```

Ejemplo de salida con hallazgos:

```
  vigil v1.0.0 — scanned 42 files

  X CRITICAL  DEP-001  requirements.txt:14
    Package 'python-jwt-utils' does not exist in pypi.
    This is likely a hallucinated dependency from an AI agent.
    -> Suggestion: Remove 'python-jwt-utils' and find the correct package name.

  X HIGH      AUTH-005  src/main.py:8
    CORS configured with '*' allowing requests from any origin.
    -> Suggestion: Restrict CORS to specific trusted origins.

  -------------------------------------------------
  42 files scanned in 1.2s
  2 findings: 1 critical, 1 high
  analyzers: dependency, auth
```

## Conceptos basicos

### Que es un finding

Un **finding** es un hallazgo de seguridad detectado por vigil. Cada finding tiene:

- **rule_id**: Identificador unico de la regla (ej. `DEP-001`, `AUTH-005`)
- **severity**: Nivel de severidad (`critical`, `high`, `medium`, `low`, `info`)
- **message**: Descripcion del problema encontrado
- **location**: Archivo y linea donde se detecto
- **suggestion**: Recomendacion concreta para corregirlo

### Niveles de severidad

| Nivel | Significado | Exit code |
|-------|-------------|-----------|
| `critical` | Debe corregirse antes de merge. Riesgo de seguridad inmediato. | 1 |
| `high` | Deberia corregirse antes de merge. Riesgo significativo. | 1 |
| `medium` | Deberia corregirse, no necesariamente antes de merge. | 0* |
| `low` | Informativo, buena practica. | 0* |
| `info` | Solo informativo, no es un problema. | 0* |

*Por defecto, vigil falla (exit code 1) con findings `high` o superiores. Esto se puede cambiar con `--fail-on`.

### Categorias

vigil organiza sus reglas en categorias:

| Categoria | Prefijo | Que detecta |
|-----------|---------|-------------|
| Dependency Hallucination | `DEP-` | Paquetes que no existen, typosquatting, paquetes sospechosamente nuevos |
| Auth & Permission | `AUTH-` | Endpoints sin auth, CORS abierto, JWT inseguro, cookies sin flags |
| Secrets & Credentials | `SEC-` | Secrets placeholder, credenciales hardcodeadas, connection strings |
| Test Quality | `TEST-` | Tests sin asserts, asserts triviales, tests skipped sin razon |

### Exit codes

| Codigo | Significado |
|--------|-------------|
| `0` | No hay findings por encima del threshold |
| `1` | Se encontraron findings por encima del threshold |
| `2` | Error de ejecucion (config invalida, error de red, etc.) |

## Que esta activo ahora

En la version actual (v1.0.0), los cuatro analyzers estan completamente funcionales:

### Dependency Analyzer (DEP-001 a DEP-007)
- Detecta paquetes que no existen en PyPI/npm (slopsquatting)
- Detecta nombres similares a paquetes populares (typosquatting)
- Verifica que las versiones pinneadas existan
- Detecta paquetes sospechosamente nuevos y sin repositorio fuente

### Auth Analyzer (AUTH-001 a AUTH-007)
- Detecta endpoints sin middleware de autenticacion
- Detecta CORS configurado con `*`
- Detecta JWT con lifetime excesivo o secret hardcodeado
- Detecta cookies sin flags de seguridad
- Detecta comparacion de passwords no timing-safe

### Secrets Analyzer (SEC-001 a SEC-006)
- Detecta placeholders copiados de documentacion o `.env.example`
- Detecta secrets con entropia baja (generados por AI)
- Detecta connection strings con credenciales embebidas
- Detecta variables de entorno con defaults sensibles

### Test Quality Analyzer (TEST-001 a TEST-006)
- Detecta tests sin assertions (test theater)
- Detecta assertions triviales (`assert True`, `toBeTruthy()`)
- Detecta catch-all de excepciones en tests
- Detecta tests skipped sin justificacion
- Detecta tests de API sin verificacion de status code
- Detecta mock mirrors (test solo prueba que el mock funciona)

```bash
# Scan completo (deps + auth + secrets + tests)
vigil scan src/

# Solo dependencias
vigil deps

# Solo calidad de tests
vigil tests tests/

# Solo checks estaticos (sin HTTP)
vigil scan src/ --offline
```

## Siguientes pasos

- Genera un archivo de configuracion: `vigil init`
- Explora todas las reglas: `vigil rules`
- Analiza solo dependencias: `vigil deps --verify`
- Analiza solo calidad de tests: `vigil tests tests/`
- Integra vigil en tu CI/CD: ver [ci-cd.md](ci-cd.md)
- Consulta los analyzers activos: ver [analizadores.md](analizadores.md)
- Consulta la referencia CLI completa: ver [cli.md](cli.md)
