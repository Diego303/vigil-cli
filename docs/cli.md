# Referencia CLI

vigil se ejecuta desde la linea de comandos. Todos los subcomandos, opciones y ejemplos se documentan a continuacion.

## Uso general

```bash
vigil [OPTIONS] COMMAND [ARGS]
```

### Opciones globales

| Opcion | Descripcion |
|--------|-------------|
| `--version` | Muestra la version de vigil |
| `--help` | Muestra la ayuda general |

---

## `vigil scan`

Comando principal. Escanea codigo en busca de problemas de seguridad especificos del codigo generado por IA.

### Sintaxis

```bash
vigil scan [PATHS...] [OPTIONS]
```

Si no se especifican paths, escanea el directorio actual (`.`).

### Opciones

| Opcion | Forma corta | Tipo | Default | Descripcion |
|--------|-------------|------|---------|-------------|
| `--config` | `-c` | PATH | Auto-detecta | Ruta al archivo `.vigil.yaml` |
| `--format` | `-f` | `human\|json\|junit\|sarif` | `human` | Formato de salida |
| `--output` | `-o` | PATH | stdout | Archivo donde escribir el reporte |
| `--fail-on` | | `critical\|high\|medium\|low` | `high` | Severidad minima para fallar (exit 1) |
| `--category` | `-C` | multiple | todas | Solo ejecutar categorias especificas |
| `--rule` | `-r` | multiple | todas | Solo ejecutar reglas especificas |
| `--exclude-rule` | `-R` | multiple | ninguna | Excluir reglas especificas |
| `--language` | `-l` | `python\|javascript` | todas | Solo escanear lenguajes especificos |
| `--offline` | | flag | false | No hacer HTTP requests a registries |
| `--changed-only` | | flag | false | Solo escanear archivos cambiados desde el ultimo commit |
| `--verbose` | `-v` | flag | false | Output detallado con logs de debug |
| `--quiet` | `-q` | flag | false | Solo mostrar findings, sin resumen |

### Ejemplos

```bash
# Scan basico
vigil scan src/

# Scan de multiples directorios
vigil scan src/ lib/ app/

# Solo dependencias y secrets
vigil scan src/ -C dependency -C secrets

# Solo una regla especifica
vigil scan src/ -r DEP-001

# Excluir reglas que no aplican a tu proyecto
vigil scan src/ -R AUTH-003 -R TEST-004

# Solo Python
vigil scan src/ -l python

# Generar reporte SARIF para GitHub Code Scanning
vigil scan src/ -f sarif -o vigil.sarif

# Generar reporte JSON
vigil scan src/ -f json -o report.json

# Generar reporte JUnit para CI dashboards
vigil scan src/ -f junit -o report.xml

# Fallar solo con findings critical
vigil scan src/ --fail-on critical

# Fallar desde medium en adelante
vigil scan src/ --fail-on medium

# Sin HTTP requests (solo checks estaticos)
vigil scan src/ --offline

# Solo archivos cambiados (ideal para pre-commit)
vigil scan --changed-only

# Con archivo de config personalizado
vigil scan src/ -c mi-vigil.yaml

# Output detallado para debugging
vigil scan src/ -v

# Guardar reporte en archivo Y mostrar en terminal (solo formato human)
vigil scan src/ -o report.txt
```

### Comportamiento del output

- **Formato `human`**: Si se especifica `--output`, el reporte se escribe al archivo Y se muestra en terminal.
- **Formatos `json`, `junit`, `sarif`**: Si se especifica `--output`, el reporte solo se escribe al archivo. Si no, se muestra en stdout.
- **`--verbose`**: Los logs de debug van a stderr. Los findings van a stdout. Nunca se mezclan.

---

## `vigil deps`

Subcomando especializado para analizar dependencias. Ejecuta solo las reglas de la categoria `dependency`.

### Sintaxis

```bash
vigil deps [PATH] [OPTIONS]
```

### Opciones

| Opcion | Forma corta | Tipo | Default | Descripcion |
|--------|-------------|------|---------|-------------|
| `--verify / --no-verify` | | flag | `--verify` | Verificar existencia de paquetes en el registry |
| `--format` | `-f` | `human\|json` | `human` | Formato de salida |
| `--offline` | | flag | false | No hacer HTTP requests |
| `--verbose` | `-v` | flag | false | Output detallado |

### Ejemplos

```bash
# Verificar dependencias del proyecto actual
vigil deps

# Verificar un proyecto especifico
vigil deps /ruta/al/proyecto

# Solo checks estaticos, sin verificar registries
vigil deps --no-verify

# Output JSON
vigil deps -f json
```

### Que archivos analiza

vigil detecta automaticamente los siguientes archivos de dependencias:

| Archivo | Ecosistema |
|---------|------------|
| `requirements.txt` | PyPI (Python) |
| `requirements-dev.txt` | PyPI (Python) |
| `requirements-test.txt` | PyPI (Python) |
| `pyproject.toml` | PyPI (Python) |
| `setup.py` | PyPI (Python) |
| `setup.cfg` | PyPI (Python) |
| `package.json` | npm (JavaScript) |

---

## `vigil tests`

Subcomando especializado para analizar calidad de tests. Ejecuta solo las reglas de la categoria `test-quality`.

### Sintaxis

```bash
vigil tests [TEST_PATHS...] [OPTIONS]
```

Si no se especifican paths, analiza el directorio `tests/`.

### Opciones

| Opcion | Forma corta | Tipo | Default | Descripcion |
|--------|-------------|------|---------|-------------|
| `--format` | `-f` | `human\|json` | `human` | Formato de salida |
| `--min-assertions` | | int | `1` | Minimo de assertions por test |
| `--offline` | | flag | false | No hacer HTTP requests a registries |
| `--verbose` | `-v` | flag | false | Output detallado |

### Ejemplos

```bash
# Analizar directorio de tests por defecto
vigil tests

# Analizar directorio especifico
vigil tests tests/ spec/

# Requerir al menos 2 assertions por test
vigil tests --min-assertions 2

# Output JSON
vigil tests -f json
```

---

## `vigil init`

Genera un archivo de configuracion `.vigil.yaml` con valores sensatos.

### Sintaxis

```bash
vigil init [PATH] [OPTIONS]
```

### Opciones

| Opcion | Tipo | Default | Descripcion |
|--------|------|---------|-------------|
| `--strategy` | `strict\|standard\|relaxed` | `standard` | Preset de configuracion |
| `--force` | flag | false | Sobrescribir archivo existente |

### Estrategias

| Estrategia | `fail_on` | `min_age_days` | `max_token_lifetime_hours` | Uso recomendado |
|------------|-----------|----------------|---------------------------|-----------------|
| `strict` | `medium` | 60 | 1 | Entornos con requisitos de compliance altos |
| `standard` | `high` | 30 | 24 | La mayoria de proyectos |
| `relaxed` | `critical` | 7 | 72 | Prototipos o proyectos en fase inicial |

### Ejemplos

```bash
# Generar config con defaults
vigil init

# Generar config estricta
vigil init --strategy strict

# Generar config en otro directorio
vigil init /ruta/al/proyecto

# Sobrescribir config existente
vigil init --force
```

---

## `vigil rules`

Lista todas las reglas disponibles con sus descripciones, severidades y referencias a estandares.

### Sintaxis

```bash
vigil rules
```

### Ejemplo de salida

```
  DEPENDENCY
  ----------------------------------------
  DEP-001    CRITICAL  Hallucinated dependency
                       Package declared as dependency does not exist in the public registry.
                       [OWASP: LLM03, CWE-829]
  DEP-002    HIGH      Suspiciously new dependency
                       Package exists but was published less than 30 days ago.
                       [OWASP: LLM03]
  ...

  AUTH
  ----------------------------------------
  AUTH-001   HIGH      Unprotected sensitive endpoint
                       Endpoint handling sensitive data without authentication middleware.
                       [OWASP: LLM06, CWE-306]
  ...
```

---

## Exit codes

Todos los subcomandos de scan (`scan`, `deps`, `tests`) usan los mismos exit codes:

| Codigo | Constante | Significado |
|--------|-----------|-------------|
| `0` | `SUCCESS` | No hay findings por encima del threshold configurado |
| `1` | `FINDINGS` | Se encontraron findings por encima del threshold |
| `2` | `ERROR` | Error de ejecucion |

### Uso en scripts

```bash
# Usar en un script de CI
vigil scan src/ --fail-on high
if [ $? -eq 1 ]; then
    echo "vigil encontro problemas de seguridad"
    exit 1
fi

# Usar con operadores logicos
vigil scan src/ && echo "Limpio" || echo "Hay findings"
```

---

## Invocacion alternativa

vigil tambien puede ejecutarse como modulo de Python:

```bash
python -m vigil scan src/
python -m vigil --help
```

Esto es util cuando `vigil` no esta en el PATH o cuando se trabaja con multiples entornos virtuales.
