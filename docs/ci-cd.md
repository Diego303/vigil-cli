# Integracion CI/CD

vigil esta disenado para integrarse facilmente en pipelines de CI/CD. Sus exit codes deterministicos, multiples formatos de salida, y modo offline lo hacen ideal para automatizacion.

## Exit codes

| Codigo | Significado |
|--------|-------------|
| `0` | No hay findings por encima del threshold |
| `1` | Findings encontrados por encima del threshold |
| `2` | Error de ejecucion |

El threshold se configura con `--fail-on` (default: `high`).

---

## GitHub Actions

### Scan basico

```yaml
name: vigil Security Scan

on:
  push:
    branches: [main]
  pull_request:

jobs:
  vigil:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install vigil
        run: pip install vigil-ai-cli

      - name: Run vigil
        run: vigil scan src/ --fail-on high
```

### Con reporte SARIF (GitHub Code Scanning)

```yaml
name: vigil SARIF

on:
  push:
    branches: [main]
  pull_request:

jobs:
  vigil:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install vigil
        run: pip install vigil-ai-cli

      - name: Run vigil
        run: vigil scan src/ -f sarif -o vigil.sarif
        continue-on-error: true

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: vigil.sarif
```

Los findings aparecen en la pestana **Security > Code scanning alerts** del repositorio.

### Con cache de dependencias

```yaml
      - name: Cache vigil registry
        uses: actions/cache@v4
        with:
          path: ~/.cache/vigil/registry/
          key: vigil-registry-${{ hashFiles('**/requirements*.txt', '**/package.json') }}
          restore-keys: |
            vigil-registry-
```

### Solo archivos cambiados en PR

```yaml
      - name: Run vigil on changed files
        run: vigil scan --changed-only --fail-on high
```

### Workflow completo recomendado

```yaml
name: vigil

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  security-scan:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-vigil-${{ hashFiles('pyproject.toml') }}

      - name: Cache vigil registry
        uses: actions/cache@v4
        with:
          path: ~/.cache/vigil/registry/
          key: vigil-registry-${{ hashFiles('**/requirements*.txt', '**/package.json') }}
          restore-keys: vigil-registry-

      - name: Install vigil
        run: pip install vigil-ai-cli

      - name: Security scan
        run: vigil scan src/ -f sarif -o vigil.sarif --fail-on high
        continue-on-error: true

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: vigil.sarif

      - name: Check exit code
        run: vigil scan src/ --fail-on high --quiet
```

---

## GitLab CI

### Scan basico

```yaml
vigil:
  image: python:3.12-slim
  stage: test
  script:
    - pip install vigil-ai-cli
    - vigil scan src/ --fail-on high
```

### Con reporte JUnit

```yaml
vigil:
  image: python:3.12-slim
  stage: test
  script:
    - pip install vigil-ai-cli
    - vigil scan src/ -f junit -o report.xml --fail-on high
  artifacts:
    reports:
      junit: report.xml
    when: always
```

Los findings aparecen en el merge request como tests fallidos en la pestana **Tests**.

### Con reporte JSON como artifact

```yaml
vigil:
  image: python:3.12-slim
  stage: test
  script:
    - pip install vigil-ai-cli
    - vigil scan src/ -f json -o vigil-report.json
  artifacts:
    paths:
      - vigil-report.json
    when: always
  allow_failure:
    exit_codes:
      - 1
```

### Pipeline completo

```yaml
stages:
  - test

vigil-full:
  image: python:3.12-slim
  stage: test
  script:
    - pip install vigil-ai-cli
    - vigil scan src/ -f junit -o report.xml
    - vigil scan src/ -f json -o report.json
  artifacts:
    reports:
      junit: report.xml
    paths:
      - report.json
    when: always
  cache:
    key: vigil-registry
    paths:
      - ~/.cache/vigil/registry/
```

---

## Azure DevOps

```yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.12'

  - script: pip install vigil-ai-cli
    displayName: 'Install vigil'

  - script: vigil scan src/ -f junit -o $(Build.ArtifactStagingDirectory)/vigil-report.xml
    displayName: 'Run vigil'
    continueOnError: true

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '**/vigil-report.xml'
    condition: always()
```

---

## Pre-commit hooks

### Con pre-commit framework

Crea o edita `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: vigil
        name: vigil security scan
        entry: vigil scan --changed-only --fail-on high --quiet
        language: python
        additional_dependencies: ['vigil-ai-cli']
        always_run: true
        pass_filenames: false
```

Instala:

```bash
pip install pre-commit
pre-commit install
```

Ahora vigil se ejecuta automaticamente antes de cada commit, escaneando solo los archivos cambiados.

### Hook manual de git

Crea `.git/hooks/pre-commit`:

```bash
#!/bin/bash
set -e

# Solo escanear archivos cambiados para rapidez
vigil scan --changed-only --fail-on high --quiet

if [ $? -eq 1 ]; then
    echo ""
    echo "vigil encontro problemas de seguridad. Corrige antes de hacer commit."
    echo "Ejecuta 'vigil scan --changed-only' para ver los detalles."
    exit 1
fi
```

```bash
chmod +x .git/hooks/pre-commit
```

### Recomendaciones para pre-commit

- Usa `--changed-only` para que el scan sea rapido (solo archivos staged).
- Usa `--quiet` para reducir output en el flujo normal.
- Usa `--offline` si no quieres que el hook dependa de conectividad a internet.
- Configura `--fail-on critical` si el scan completo es muy estricto para el flujo de desarrollo local.

---

## Quality gates

### Estrategia por entorno

```bash
# Desarrollo local (pre-commit): solo bloquear criticos
vigil scan --changed-only --fail-on critical --quiet

# PR / merge request: bloquear high y superiores
vigil scan src/ --fail-on high

# Release / produccion: bloquear desde medium
vigil scan src/ --fail-on medium --config .vigil.strict.yaml
```

### Con archivos de config dedicados

```
proyecto/
  .vigil.yaml              # Config por defecto (standard)
  .vigil.strict.yaml       # Config para CI de produccion
  .vigil.dev.yaml          # Config para desarrollo local
```

```bash
# CI
vigil scan src/ --config .vigil.strict.yaml

# Local
vigil scan src/ --config .vigil.dev.yaml
```

### Fail-on progresivo

Una estrategia efectiva es empezar relajado e ir subiendo la exigencia:

1. **Semana 1**: `--fail-on critical` — solo bloquear dependencias alucinadas y secrets criticos.
2. **Semana 2**: `--fail-on high` — agregar endpoints sin auth, CORS abierto.
3. **Semana 3**: `--fail-on medium` — agregar cookies inseguras, tests triviales.

Esto evita que vigil bloquee al equipo cuando se introduce por primera vez.

---

## Modo offline

En entornos sin acceso a internet (runners aislados, air-gapped environments):

```bash
vigil scan src/ --offline
```

En modo offline, vigil:
- No hace HTTP requests a PyPI ni npm.
- Ejecuta todos los checks estaticos que no requieren red.
- **Si ejecuta:** DEP-003 (typosquatting por similaridad de nombres — no requiere red).
- **No ejecuta:** DEP-001 (paquete inexistente), DEP-002 (paquete nuevo), DEP-005 (sin repo fuente), DEP-007 (version inexistente).
- Los analyzers futuros (auth, secrets, tests) seran completamente estaticos y funcionaran en modo offline.

Esto es util en:
- Runners de CI sin acceso a internet.
- Entornos corporativos con proxies restrictivos.
- Ejecuciones donde la velocidad es critica (sin latencia de red).

---

## Integracion con otras herramientas

### Con tox

```ini
# tox.ini
[testenv:security]
deps = vigil-ai-cli
commands = vigil scan src/ --fail-on high
```

### Con Makefile

```makefile
.PHONY: security
security:
	vigil scan src/ --fail-on high

.PHONY: security-report
security-report:
	vigil scan src/ -f json -o reports/vigil.json
	vigil scan src/ -f sarif -o reports/vigil.sarif
```

### Con nox (Python)

```python
# noxfile.py
import nox

@nox.session
def security(session):
    session.install("vigil-ai-cli")
    session.run("vigil", "scan", "src/", "--fail-on", "high")
```
