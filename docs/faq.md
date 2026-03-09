# FAQ y Troubleshooting

Preguntas frecuentes y solucion a problemas comunes.

---

## General

### vigil usa IA para detectar problemas?

No. vigil es **100% determinista**. Usa reglas estaticas, regex y verificacion de registries. No hace llamadas a APIs de IA, no tiene costos de inferencia, y el mismo codigo siempre produce los mismos resultados.

### Que lenguajes soporta?

Python y JavaScript/TypeScript. Los archivos de dependencias soportados son `requirements.txt`, `pyproject.toml`, `package.json`. Los analyzers de auth, secrets y test quality analizan archivos `.py`, `.js`, `.ts`, `.jsx`, `.tsx`.

### vigil reemplaza a Semgrep/Snyk/SonarQube?

No. vigil detecta problemas **especificos del codigo generado por IA** que esas herramientas no cubren. Es complementario:

| Problema | vigil | Semgrep | Snyk | Gitleaks |
|----------|-------|---------|------|----------|
| Paquete alucinado (no existe) | Si | No | No | No |
| Typosquatting | Si | No | Parcial | No |
| Placeholder secret (`"changeme"`) | Si | Parcial | No | No |
| Secret real filtrado | No | No | No | Si |
| CVE conocida en dependencia | No | No | Si | No |
| SQL injection | No | Si | No | No |

### Cuantas reglas tiene?

26 definidas, 24 implementadas. Las 2 pendientes son DEP-004 (paquetes con pocas descargas — requiere API de estadisticas) y DEP-006 (imports no declarados en dependencias — requiere parsing de imports AST).

---

## Instalacion y setup

### Que version de Python necesito?

Python 3.12 o superior. vigil usa `tomllib` de la stdlib (disponible desde 3.11) y sintaxis `str | None` (disponible desde 3.10), pero el target oficial es 3.12+.

### Como instalo en modo desarrollo?

```bash
git clone https://github.com/org/vigil.git
cd vigil
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
vigil --version
```

### El comando `vigil` no se encuentra despues de instalar

Asegurate de que el entorno virtual esta activado (`source .venv/bin/activate`) o que el directorio de scripts de pip esta en tu PATH. Alternativa: `python -m vigil`.

---

## Dependencias y registry

### Que hace vigil con las HTTP requests?

Solo hace GET requests a las APIs publicas de PyPI (`pypi.org/pypi/{name}/json`) y npm (`registry.npmjs.org/{name}`) para verificar que los paquetes existen. **No envia codigo fuente ni datos del proyecto** — solo nombres de paquetes.

### Como evito las HTTP requests?

```bash
vigil scan src/ --offline
```

En modo offline se omiten DEP-001, DEP-002, DEP-005 y DEP-007 (requieren registry). DEP-003 (typosquatting) sigue funcionando porque usa un corpus local.

### Cual es la diferencia entre `--offline` y `--no-verify`?

`--offline` desactiva **todas** las HTTP requests del scan completo (aplica a todos los analyzers). `--no-verify` es especifico del subcomando `vigil deps` y desactiva solo la verificacion de existencia en registries.

En la practica, para un `vigil scan`, usa `--offline`. Para `vigil deps`, puedes usar `--no-verify` o `--offline`.

### El cache del registry ocupa mucho espacio?

No. Cada paquete se cachea como un archivo JSON individual en `~/.cache/vigil/registry/`. Un proyecto con 100 dependencias genera ~100 archivos de ~1-2 KB cada uno.

### Como limpio el cache?

```bash
rm -rf ~/.cache/vigil/registry/
```

### Como fuerzo requests frescas sin borrar el cache?

Configura `cache_ttl_hours: 0` en `.vigil.yaml`:

```yaml
deps:
  cache_ttl_hours: 0
```

### vigil reporta un paquete como inexistente pero si existe

Posibles causas:
1. **Cache stale**: Limpia el cache con `rm -rf ~/.cache/vigil/registry/` y vuelve a ejecutar.
2. **Problema de red temporal**: Si la request fallo durante el scan, vigil asume que el paquete existe (para evitar falsos positivos). Re-ejecuta.
3. **Nombre normalizado**: PyPI trata `my-package`, `my_package` y `my.package` como equivalentes. Verifica que el nombre en tu `requirements.txt` coincide con el nombre oficial en pypi.org.

---

## Falsos positivos

### AUTH-002 salta en mi endpoint `/login` — es un falso positivo?

Es **por diseno**. AUTH-002 detecta endpoints mutantes (POST/PUT/DELETE) sin auth middleware. Un POST `/login` no tiene auth porque es el punto de entrada — pero vigil no puede distinguirlo de un POST `/delete-account` sin auth.

**Solucion:** Deshabilitar AUTH-002 para ese caso, o reducir su severidad:

```yaml
rules:
  AUTH-002:
    severity: "medium"  # No bloquea el CI
```

### AUTH-005 (CORS) salta en archivos de desarrollo/test

vigil tiene una heuristica que suprime AUTH-005 en archivos dentro de directorios de dev/test (`dev/`, `test/`, `tests/`, `local/`, `example/`) o con prefijos de dev (`dev_`, `test_`, `local_`). Si tu archivo esta fuera de estos paths:

```yaml
auth:
  cors_allow_localhost: true  # Suprime AUTH-005 en paths de dev/test
```

O deshabilita la regla directamente:

```yaml
rules:
  AUTH-005:
    enabled: false
```

### SEC-001 detecta un valor que no es un placeholder

Los patrones de placeholder son regex configurables. Si un patron genera falsos positivos en tu proyecto, puedes personalizar la lista en `.vigil.yaml`:

```yaml
secrets:
  placeholder_patterns:
    - "changeme"
    - "your-.*-here"
    # ... solo los patrones que necesites
```

### TEST-002 (assertion trivial) salta en tests que verifican existencia

`assert x is not None` se considera trivial si es la **unica** assertion del test. Si tu test tiene assertions adicionales significativas, TEST-002 no salta.

Si la verificacion de existencia es intencionalmente tu unico assertion:

```yaml
rules:
  TEST-002:
    severity: "low"
```

### Como suprimo una regla para todo el proyecto?

```yaml
# .vigil.yaml
rules:
  RULE-ID:
    enabled: false
```

### Como cambio la severidad de una regla sin deshabilitarla?

```yaml
rules:
  AUTH-005:
    severity: "low"  # Sigue detectando pero no bloquea con --fail-on high
```

### `--rule` no muestra findings de una regla deshabilitada en config

Si, lo hace. Desde v1.0.0, `--rule DEP-001` tiene prioridad sobre `enabled: false` en `.vigil.yaml`. El flag CLI siempre gana sobre la config YAML.

---

## Rendimiento

### El scan es lento con muchas dependencias

La verificacion de registry (DEP-001, DEP-002, DEP-005, DEP-007) hace una HTTP request por paquete. Para proyectos con muchas dependencias:

1. **Usa cache**: Las ejecuciones posteriores son rapidas (TTL 24h por defecto).
2. **Usa `--offline`**: Solo ejecuta checks estaticos — instantaneo.
3. **Limita categorias**: `vigil scan src/ -C auth -C secrets` si solo necesitas esos checks.

### El scan de typosquatting (DEP-003) es lento

El corpus tiene 8400+ paquetes. Para 200+ dependencias, el scan puede tomar ~20 segundos. vigil usa early rejection basado en longitud para optimizar, pero proyectos con cientos de dependencias son inherentemente mas lentos.

**Mitigacion**: En pre-commit hooks, usa `--changed-only` para solo verificar archivos modificados.

### Archivos grandes o binarios ralentizan el scan

vigil excluye automaticamente directorios como `.venv/`, `node_modules/`, `.git/`, `dist/`, `build/`, `__pycache__/`. Si tienes otros directorios con archivos grandes:

```yaml
exclude:
  - "data/"
  - "assets/"
  - "vendor/"
```

---

## Encoding y archivos

### vigil crashea con archivos no-UTF8

No deberia. Los analyzers usan `errors="replace"` al leer archivos, lo que reemplaza bytes invalidos con el caracter de reemplazo Unicode. Si encuentras un crash por encoding, reportalo como bug.

### vigil analiza archivos binarios?

No. Solo analiza archivos con extensiones de texto conocidas (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.txt`, `.toml`, `.json`, `.yaml`, `.yml`). Los binarios, imagenes y archivos compilados se ignoran.

### vigil detecta problemas en archivos vacios?

No. Un archivo vacio no genera findings.

---

## Configuracion

### Que pasa si mi `.vigil.yaml` tiene un error de sintaxis?

vigil reporta un error claro y sale con exit code 2:

```
Error: Config file .vigil.yaml: invalid fail_on 'extreme'. Must be one of: critical, high, info, low, medium
```

### Que pasa si no tengo `.vigil.yaml`?

vigil funciona con defaults sensatos:
- `fail_on: "high"`
- Todos los analyzers activos
- Todos los lenguajes
- Registry verification habilitada
- Cache TTL de 24 horas

### Puedo tener configs diferentes para CI y desarrollo local?

Si. Crea multiples archivos y usa `--config`:

```bash
# Local
vigil scan src/

# CI
vigil scan src/ --config .vigil.strict.yaml
```

### Que estrategias predefinidas hay?

| Estrategia | `fail_on` | `min_age_days` | `max_token_lifetime_hours` |
|------------|-----------|----------------|---------------------------|
| `strict` | `medium` | 60 | 1 |
| `standard` | `high` | 30 | 24 |
| `relaxed` | `critical` | 7 | 72 |

```bash
vigil init --strategy strict
```

---

## CI/CD

### Como hago que vigil no bloquee mi pipeline mientras adopto la herramienta?

Estrategia progresiva:

```bash
# Semana 1: solo criticos
vigil scan src/ --fail-on critical

# Semana 2: agregar high
vigil scan src/ --fail-on high

# Semana 3: cobertura completa
vigil scan src/ --fail-on medium
```

### Puedo usar vigil con GitHub Code Scanning?

Si. Genera un reporte SARIF y subelo:

```yaml
- run: vigil scan src/ -f sarif -o vigil.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: vigil.sarif
```

Los findings aparecen en Security > Code scanning alerts.

### El pre-commit hook es muy lento

Usa `--changed-only --offline --quiet` para minimizar el tiempo:

```bash
vigil scan --changed-only --offline --fail-on critical --quiet
```

Esto solo analiza archivos staged, no hace HTTP requests, y solo muestra findings.

---

## Exit codes

### Que significan los exit codes?

| Codigo | Significado |
|--------|-------------|
| `0` | No hay findings por encima del threshold |
| `1` | Findings encontrados por encima del threshold |
| `2` | Error de ejecucion (config invalida, path inexistente, etc.) |

### vigil retorna exit 1 pero no veo findings criticos

El threshold por defecto es `high`, no `critical`. Findings de severidad HIGH tambien causan exit code 1. Usa `--fail-on critical` si solo quieres bloquear en criticos.

### vigil retorna exit 0 pero hay findings en el output

Los findings que ves estan por debajo del threshold configurado. Por ejemplo, con `--fail-on high`, findings de severidad MEDIUM y LOW aparecen en el output pero no causan exit code 1.
