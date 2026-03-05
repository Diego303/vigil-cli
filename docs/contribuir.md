# Contribuir

Guia para contribuir al desarrollo de vigil.

## Setup de desarrollo

### Requisitos

- Python 3.12 o superior
- git
- pip

### Clonar y configurar

```bash
git clone https://github.com/org/vigil.git
cd vigil

# Crear entorno virtual
python3.12 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

# Instalar en modo desarrollo con dependencias de dev
pip install -e ".[dev]"

# Verificar instalacion
vigil --version
```

### Verificar que todo funciona

```bash
# Ejecutar tests
pytest

# Ejecutar vigil
vigil scan src/
vigil rules
```

---

## Estructura del proyecto

```
src/vigil/
  cli.py              # Comandos Click
  config/             # Configuracion (schema, loader, rules)
  core/               # Modelos y motor (finding, engine, file_collector)
  analyzers/          # Analyzers (logica de deteccion)
  reports/            # Formateadores de salida
  logging/            # Setup de structlog
tests/
  test_cli.py         # Tests del CLI
  test_core/          # Tests del core
  test_config/        # Tests de configuracion
  test_reports/       # Tests de formateadores
  fixtures/           # Archivos de prueba
docs/                 # Documentacion
```

---

## Convenciones de codigo

### Python

- **Version**: Python 3.12+. Usar `str | None` en lugar de `Optional[str]`.
- **Type hints**: Todas las funciones publicas deben tener type hints completos.
- **Linter**: ruff con target `py312` y line-length 100.
- **Formatter**: ruff format.

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

### Nomenclatura

- Clases: `PascalCase` (`ScanEngine`, `HumanFormatter`).
- Funciones y variables: `snake_case` (`collect_files`, `rule_id`).
- Constantes: `UPPER_SNAKE_CASE` (`SEVERITY_SORT_ORDER`, `LANGUAGE_EXTENSIONS`).
- Archivos: `snake_case.py`.

### Imports

Orden: stdlib, third-party, local. Ruff se encarga de ordenarlos.

```python
import json
from pathlib import Path

import structlog
from pydantic import BaseModel

from vigil.core.finding import Finding, Severity
```

### Logging

- Usar `structlog` siempre. Nunca `print()`.
- Logs van a stderr (nunca a stdout).
- Mensajes como keys snake_case: `logger.info("files_collected", count=42)`.

### Modelos

- **Pydantic v2**: Para configuracion del usuario (requiere validacion).
- **dataclasses**: Para modelos internos (Finding, Location, RuleDefinition).
- **Protocol**: Para interfaces (BaseAnalyzer, BaseFormatter).

---

## Como implementar un analyzer

Los analyzers son la logica de deteccion de vigil. Cada analyzer implementa el protocolo `BaseAnalyzer`.

### Paso 1: Crear el archivo

```bash
# Ejemplo: analyzer de secrets
touch src/vigil/analyzers/secrets.py
```

### Paso 2: Implementar el protocolo

```python
"""Analyzer de secrets y credenciales."""

import structlog

from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity

logger = structlog.get_logger()


class SecretsAnalyzer:
    """Detecta secrets hardcodeados y placeholders."""

    @property
    def name(self) -> str:
        return "secrets"

    @property
    def category(self) -> Category:
        return Category.SECRETS

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        findings: list[Finding] = []

        for file_path in files:
            if not file_path.endswith(".py"):
                continue
            try:
                with open(file_path) as f:
                    content = f.read()
                findings.extend(self._check_file(file_path, content, config))
            except OSError:
                logger.warning("file_read_error", file=file_path)

        return findings

    def _check_file(
        self, file_path: str, content: str, config: ScanConfig
    ) -> list[Finding]:
        findings: list[Finding] = []
        # ... implementar checks ...
        return findings
```

### Paso 3: Registrar en el engine

En `cli.py`, el analyzer se registra antes de ejecutar el scan:

```python
from vigil.analyzers.secrets import SecretsAnalyzer

engine = ScanEngine(config)
engine.register_analyzer(SecretsAnalyzer())
result = engine.run(paths)
```

### Paso 4: Escribir tests

```python
# tests/test_analyzers/test_secrets.py
from vigil.analyzers.secrets import SecretsAnalyzer
from vigil.config.schema import ScanConfig


def test_detects_placeholder_secret(tmp_path):
    # Crear archivo de prueba
    test_file = tmp_path / "app.py"
    test_file.write_text('SECRET_KEY = "your-api-key-here"\n')

    analyzer = SecretsAnalyzer()
    config = ScanConfig()
    findings = analyzer.analyze([str(test_file)], config)

    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-001"
    assert findings[0].severity.value == "critical"
```

### Reglas del analyzer

1. **Determinista**: Mismo input = mismo output. Sin aleatoridad.
2. **Sin side effects**: No modificar archivos, no escribir a stdout.
3. **Robusto**: Capturar errores de I/O por archivo, no por scan completo.
4. **Eficiente**: Leer cada archivo una sola vez, usar early returns.
5. **Configurable**: Respetar thresholds y opciones de `ScanConfig`.

---

## Como agregar una regla

### Paso 1: Definir en el catalogo

En `src/vigil/config/rules.py`, agregar a la lista `RULES_V0`:

```python
RuleDefinition(
    id="SEC-007",
    name="My new rule",
    description="Description of what this rule detects.",
    category=Category.SECRETS,
    default_severity=Severity.HIGH,
    owasp_ref="LLM02",
    cwe_ref="CWE-798",
),
```

### Paso 2: Implementar la deteccion

En el analyzer correspondiente, agregar la logica que crea `Finding` con `rule_id="SEC-007"`.

### Paso 3: Agregar tests

- Test positivo: codigo vulnerable es detectado.
- Test negativo: codigo seguro no genera findings.
- Test de configuracion: la regla respeta overrides.

### Paso 4: Documentar

Agregar la regla a `docs/reglas.md` con:
- Severidad y referencias OWASP/CWE.
- Que detecta.
- Ejemplo de codigo vulnerable.
- Como corregirlo.

---

## Tests

### Ejecutar

```bash
# Todos los tests
pytest

# Con cobertura
pytest --cov=vigil --cov-report=term-missing

# Un archivo especifico
pytest tests/test_core/test_engine.py

# Un test especifico
pytest tests/test_core/test_engine.py::test_engine_no_analyzers

# Verbose
pytest -v
```

### Estructura de tests

- Cada modulo tiene su directorio de tests correspondiente.
- Fixtures globales en `tests/conftest.py`.
- Archivos de prueba en `tests/fixtures/`.

### Convenciones de tests

- Nombres descriptivos: `test_detects_placeholder_secret`, no `test_1`.
- Un assert logico por test (puede ser multiples `assert` si verifican la misma cosa).
- Usar `tmp_path` de pytest para archivos temporales.
- Usar fixtures para configuraciones reutilizables.
- No usar mocks excepto para I/O externo (HTTP, filesystem).

### Cobertura actual

| Modulo | Tests |
|--------|-------|
| CLI | 19 |
| Core (finding) | 12 |
| Core (engine) | 12 |
| Core (file_collector) | 11 |
| Config (schema) | 13 |
| Config (loader) | 15 |
| Config (rules) | 14 |
| Reports (formatters) | 19 |
| **Total** | **125** |

---

## Pull requests

### Proceso

1. Crear un branch desde `develop`: `git checkout -b feature/mi-feature develop`
2. Hacer los cambios.
3. Ejecutar tests: `pytest`
4. Ejecutar linter: `ruff check src/ tests/`
5. Crear PR hacia `develop`.

### Checklist del PR

- [ ] Los tests pasan: `pytest`
- [ ] El linter pasa: `ruff check src/ tests/`
- [ ] Se agregaron tests para la nueva funcionalidad.
- [ ] La documentacion se actualizo si aplica.
- [ ] El CHANGELOG.md se actualizo.

### Commits

- Mensajes claros y descriptivos en ingles.
- Usar verbos en imperativo: "Add", "Fix", "Remove", no "Added", "Fixed".
- Prefijos utiles: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.

```
feat: add secrets analyzer with SEC-001 and SEC-002
fix: handle empty requirements.txt in dependency analyzer
docs: add architecture documentation
test: add tests for SARIF formatter edge cases
```

---

## Fases de desarrollo

vigil se desarrolla en fases incrementales:

| Fase | Descripcion | Estado |
|------|-------------|--------|
| **FASE 0** | Scaffolding, config, engine, CLI, formatters, rule catalog | Completada |
| **FASE 1** | Dependency analyzer (DEP-001 a DEP-007) | Pendiente |
| **FASE 2** | Auth analyzer (AUTH-001 a AUTH-007) | Pendiente |
| **FASE 3** | Secrets analyzer (SEC-001 a SEC-006) | Pendiente |
| **FASE 4** | Test quality analyzer (TEST-001 a TEST-006) | Pendiente |
| **FASE 5** | Integracion, polish, release | Pendiente |

Consultar `SEGUIMIENTO-V0.md` para el estado detallado de cada fase.

---

## Contacto

- **Issues**: Reportar bugs y sugerir features en el repositorio de GitHub.
- **PRs**: Siempre bienvenidos. Para cambios grandes, abrir un issue primero para discutir el enfoque.
