# Arquitectura

Este documento describe la estructura interna de vigil, el flujo del motor de analisis, y el protocolo de analyzers.

## Estructura del proyecto

```
vigil-cli/
  src/vigil/
    __init__.py                   # __version__
    cli.py                        # Comandos Click (scan, deps, tests, init, rules)
    config/
      __init__.py
      schema.py                   # Modelos Pydantic v2 para configuracion
      loader.py                   # Carga y merge de config (YAML + CLI)
      rules.py                    # Catalogo de 26 reglas (RULES_V0)
    core/
      __init__.py
      finding.py                  # Severity, Category, Location, Finding
      engine.py                   # ScanEngine, ScanResult
      file_collector.py           # Descubrimiento de archivos
      rule_registry.py            # RuleRegistry para acceso a reglas
    analyzers/
      __init__.py
      base.py                     # BaseAnalyzer Protocol
    reports/
      __init__.py
      formatter.py                # BaseFormatter Protocol + factory
      human.py                    # Formato terminal con colores
      json_fmt.py                 # Formato JSON estructurado
      junit.py                    # Formato JUnit XML
      sarif.py                    # Formato SARIF 2.1.0
      summary.py                  # Generador de resumen (conteos)
    logging/
      __init__.py
      setup.py                    # Configuracion de structlog
  tests/
    conftest.py                   # Fixtures globales
    test_cli.py                   # Tests del CLI
    test_core/
      test_finding.py
      test_engine.py
      test_file_collector.py
    test_config/
      test_schema.py
      test_loader.py
      test_rules.py
    test_reports/
      test_formatters.py
    fixtures/                     # Archivos de prueba
```

---

## Modelos de datos

### Severity

Enum string con 5 niveles, ordenados de mayor a menor criticidad:

```python
class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
```

Usar `str, Enum` permite comparar directamente con strings y serializar a JSON sin conversion.

### Category

Enum string con 4 categorias de analisis:

```python
class Category(str, Enum):
    DEPENDENCY = "dependency"
    AUTH = "auth"
    SECRETS = "secrets"
    TEST_QUALITY = "test-quality"
```

### Location

Dataclass que indica donde se encontro el problema:

```python
@dataclass
class Location:
    file: str                    # Ruta al archivo
    line: int | None = None      # Linea (1-based)
    column: int | None = None    # Columna (1-based)
    end_line: int | None = None  # Linea final (para rangos)
    snippet: str | None = None   # Fragmento de codigo
```

### Finding

Dataclass que representa un hallazgo individual:

```python
@dataclass
class Finding:
    rule_id: str                        # "DEP-001", "AUTH-005"
    category: Category                  # Category.DEPENDENCY
    severity: Severity                  # Severity.CRITICAL
    message: str                        # Descripcion del problema
    location: Location                  # Donde se encontro
    suggestion: str | None = None       # Como corregirlo
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocking(self) -> bool:
        return self.severity in (Severity.CRITICAL, Severity.HIGH)
```

La propiedad `is_blocking` determina si el finding deberia bloquear un merge (por defecto, CRITICAL y HIGH son bloqueantes).

---

## Flujo del motor

El `ScanEngine` es el orquestador central. Su metodo `run()` ejecuta el pipeline completo:

```
                    run(paths)
                       |
            +----------v-----------+
            |  1. Collect files    |
            |  (file_collector)    |
            +----------+-----------+
                       |
            +----------v-----------+
            |  2. Run analyzers    |
            |  (for each analyzer) |
            +----------+-----------+
                       |
            +----------v-----------+
            |  3. Apply overrides  |
            |  (rule_overrides)    |
            +----------+-----------+
                       |
            +----------v-----------+
            |  4. Sort findings    |
            |  (by severity)       |
            +----------+-----------+
                       |
                       v
                  ScanResult
```

### Paso 1: Recopilar archivos

`file_collector.collect_files()` recibe las rutas del usuario y retorna una lista de archivos a escanear:

- Resuelve directorios recursivamente con `Path.rglob("*")`.
- Filtra por extensiones de lenguaje (`LANGUAGE_EXTENSIONS`).
- Excluye patrones configurados (`node_modules/`, `.venv/`, etc.).
- Siempre incluye archivos de dependencias (`requirements.txt`, `package.json`, etc.) independientemente del filtro de lenguaje.
- Deduplica preservando el orden.

### Paso 2: Ejecutar analyzers

Para cada analyzer registrado:

1. Verifica si debe ejecutarse (`_should_run()`): respeta filtros de `--category` y `--rule`.
2. Llama a `analyzer.analyze(files, config)`.
3. Recopila los findings retornados.
4. Captura excepciones por analyzer (un analyzer fallido no detiene a los demas).

### Paso 3: Aplicar overrides

`_apply_rule_overrides()` procesa la seccion `rules:` de la configuracion:

- Si una regla tiene `enabled: false`, sus findings se eliminan.
- Si una regla tiene `severity: "low"`, la severidad del finding se modifica.
- Si una regla esta en `exclude_rules` (de `--exclude-rule`), se elimina.

### Paso 4: Ordenar

Los findings se ordenan por severidad descendente (CRITICAL primero, INFO ultimo) usando `SEVERITY_SORT_ORDER`.

---

## Protocolo de analyzers

Cada analyzer implementa el protocolo `BaseAnalyzer`:

```python
class BaseAnalyzer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def category(self) -> Category: ...

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]: ...
```

### Contrato

- **`name`**: Nombre unico del analyzer (ej. `"dependency"`, `"auth"`).
- **`category`**: Categoria de findings que genera.
- **`analyze()`**: Recibe la lista de archivos y la configuracion, retorna findings.

### Reglas para implementar un analyzer

1. **Determinista**: El mismo input siempre produce el mismo output.
2. **Sin efectos secundarios**: No modifica archivos, no escribe a stdout.
3. **Manejo de errores interno**: Si un archivo no se puede leer, el analyzer lo ignora y continua.
4. **Logging a stderr**: Usar `structlog` para logs de debug/info.
5. **Respetar la configuracion**: Leer thresholds y opciones de `ScanConfig`.

### Ejemplo de implementacion

```python
from vigil.analyzers.base import BaseAnalyzer
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity

class DependencyAnalyzer:
    @property
    def name(self) -> str:
        return "dependency"

    @property
    def category(self) -> Category:
        return Category.DEPENDENCY

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        findings: list[Finding] = []
        # ... logica de analisis ...
        return findings
```

No se requiere herencia — solo satisfacer el Protocol (structural typing).

---

## Sistema de configuracion

### Tres capas con merge progresivo

```
Defaults (schema.py) < Archivo YAML (.vigil.yaml) < Flags CLI
```

1. **Defaults**: Definidos como valores por defecto en los modelos Pydantic (`ScanConfig`, `DepsConfig`, etc.).
2. **YAML**: Cargado con `pyyaml` y validado con Pydantic.
3. **CLI**: Flags de Click que sobreescriben campos especificos.

### Loader

`load_config()` en `config/loader.py`:

1. Busca el archivo de config (manual con `--config`, o auto-deteccion subiendo por el arbol de directorios).
2. Parsea el YAML.
3. Crea una instancia de `ScanConfig` con los valores del YAML.
4. Aplica overrides del CLI sobre la instancia.
5. Retorna la configuracion final.

### Validacion

Pydantic v2 valida automaticamente:
- Tipos de datos (`min_age_days` es int, no string).
- Valores validos (`fail_on` es uno de critical/high/medium/low).
- Modelos anidados (`deps`, `auth`, `secrets`, `tests`, `output`).

---

## Catalogo de reglas

Las 26 reglas estan definidas en `config/rules.py` como instancias de `RuleDefinition`:

```python
@dataclass
class RuleDefinition:
    id: str                              # "DEP-001"
    name: str                            # "Hallucinated dependency"
    description: str                     # Descripcion larga
    category: Category                   # Category.DEPENDENCY
    default_severity: Severity           # Severity.CRITICAL
    enabled_by_default: bool = True
    languages: list[str] | None = None   # None = todos
    owasp_ref: str | None = None         # "LLM03"
    cwe_ref: str | None = None           # "CWE-829"
```

### RuleRegistry

Provee acceso indexado al catalogo:

- `registry.get("DEP-001")` — obtener una regla por ID.
- `registry.all()` — todas las reglas.
- `registry.by_category(Category.AUTH)` — reglas de una categoria.
- `registry.by_severity(Severity.CRITICAL)` — reglas de una severidad.
- `registry.enabled_rules(overrides)` — reglas habilitadas despues de aplicar overrides.

---

## Formateadores

### Protocolo

```python
class BaseFormatter(Protocol):
    def format(self, result: ScanResult) -> str: ...
```

### Factory

`get_formatter(format_name)` retorna la clase correcta con lazy import:

```python
"human"  -> HumanFormatter
"json"   -> JsonFormatter
"junit"  -> JunitFormatter
"sarif"  -> SarifFormatter
```

### Flujo de output

```
ScanResult -> Formatter.format() -> string -> stdout o archivo
```

El CLI decide a donde enviar el output:
- Sin `--output`: stdout.
- Con `--output`: escribe a archivo (y tambien a stdout para formato human).

---

## Logging

### structlog

vigil usa `structlog` para logging estructurado:

- **Verbose mode** (`-v`): Level DEBUG, con timestamps y key-value pairs.
- **Normal mode**: Level WARNING, output minimalista.
- **Output siempre a stderr**: Los logs nunca van a stdout. Esto permite `vigil scan -f json | jq` sin contaminar el JSON con logs.

### Ejemplo de logs en modo verbose

```
2024-01-15 10:30:00 [info] files_collected count=42
2024-01-15 10:30:00 [info] analyzer_start name=dependency
2024-01-15 10:30:01 [info] analyzer_done name=dependency findings=2
```

---

## Dependencias externas

| Dependencia | Version | Proposito |
|-------------|---------|-----------|
| `click>=8.1` | CLI framework | Subcomandos, opciones, help automatico |
| `pydantic>=2.0` | Validacion | Modelos de configuracion con validacion |
| `httpx>=0.27` | HTTP client | Requests a PyPI/npm (async-capable) |
| `structlog>=24.1` | Logging | Logging estructurado a stderr |
| `pyyaml>=6.0` | YAML parser | Carga de archivos de configuracion |

### Dependencias de desarrollo

| Dependencia | Version | Proposito |
|-------------|---------|-----------|
| `pytest>=8.0` | Testing | Framework de tests |
| `pytest-cov>=5.0` | Cobertura | Reporte de cobertura de tests |
| `ruff>=0.4` | Linting | Linter y formatter de Python |

---

## Decisiones de diseno

### Por que Protocol y no ABC

Se usa `typing.Protocol` (structural typing) en lugar de `abc.ABC` (nominal typing) para:

- **Flexibilidad**: Los analyzers no necesitan heredar de una clase base.
- **Testing**: Es trivial crear fakes/mocks que satisfagan el protocolo.
- **Desacoplamiento**: Los modulos no dependen de la clase base.

### Por que dataclasses y no Pydantic para Finding

- `Finding`, `Location`, y `RuleDefinition` son **modelos de datos internos** que no necesitan validacion.
- Pydantic se reserva para la **configuracion del usuario** donde la validacion es critica.
- Las dataclasses son mas ligeras y rapidas para datos que se crean internamente.

### Por que structlog

- Logging estructurado (key-value) facilita parsing y filtrado.
- Separacion clara de output (stdout) vs logs (stderr).
- Configuracion centralizada con processors.

### Por que no async

vigil V0 es sincrono. Las razones:

- La mayoria de operaciones son I/O de filesystem, que es rapido.
- Las HTTP requests al registry se pueden hacer con `httpx` sincrono.
- La simplicidad del codigo sincrono facilita debugging y testing.
- Se puede migrar a async en versiones futuras si el rendimiento lo requiere.
