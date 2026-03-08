# Formatos de salida

vigil soporta 4 formatos de salida para adaptarse a diferentes flujos de trabajo: terminal interactiva, automatizacion, dashboards de CI, y plataformas de seguridad.

## Seleccion de formato

```bash
# Formato human (default)
vigil scan src/

# Formato JSON
vigil scan src/ -f json

# Formato JUnit XML
vigil scan src/ -f junit

# Formato SARIF 2.1.0
vigil scan src/ -f sarif
```

---

## Human

Formato por defecto, optimizado para lectura en terminal. Incluye colores ANSI, iconos de severidad y un resumen final.

### Iconos de severidad

| Icono | Severidad | Color |
|-------|-----------|-------|
| `✗` | CRITICAL | Rojo |
| `✗` | HIGH | Rojo |
| `⚠` | MEDIUM | Amarillo |
| `~` | LOW | Azul |
| `i` | INFO | Cyan |

### Ejemplo de salida

```
  vigil v0.6.0 — scanning 42 files...

  ✗ CRITICAL  DEP-001  requirements.txt:14
    Package 'python-jwt-utils' does not exist in pypi.
    → Suggestion: Remove 'python-jwt-utils' and find the correct package name.
    | python-jwt-utils==1.0.0

  ✗ HIGH      AUTH-005  src/main.py:8
    CORS configured with '*' allowing requests from any origin.
    → Suggestion: Restrict CORS to specific trusted origins.

  ─────────────────────────────────────────────────
  42 files scanned in 1.2s
  2 findings: 1 critical, 1 high
  2 analyzers: dependency ✓, auth ✓
```

### Salida limpia (sin findings)

```
  vigil v0.6.0 — scanning 42 files...

  No findings.

  ─────────────────────────────────────────────────
  42 files scanned in 0.5s
  0 findings
  2 analyzers: dependency ✓, auth ✓
```

### Colores

- Los colores se activan automaticamente cuando stdout es un TTY (terminal interactiva).
- Si stdout es un pipe o un archivo, los colores se desactivan automaticamente.
- Puedes controlar esto con la config `output.colors`.

### Snippets

Si un finding incluye un `snippet` (fragmento de codigo), se muestra debajo de la sugerencia con el prefijo `|`.

### Modo quiet

Con `output.quiet: true` (o la config equivalente), el formato human suprime header y resumen, mostrando solo los findings y errores. Util para integraciones que solo necesitan la lista de problemas.

### Comportamiento con `--output`

Cuando se usa `--output` con formato human, el reporte se escribe tanto al archivo como a la terminal. Esto permite guardar el reporte sin perder feedback inmediato.

---

## JSON

Formato estructurado para procesamiento programatico, integracion con otras herramientas, o almacenamiento.

### Estructura

```json
{
  "version": "0.6.0",
  "files_scanned": 42,
  "duration_seconds": 1.2,
  "analyzers_run": ["dependency", "auth"],
  "findings_count": 2,
  "findings": [
    {
      "rule_id": "DEP-001",
      "category": "dependency",
      "severity": "critical",
      "message": "Package 'python-jwt-utils' does not exist in pypi.",
      "location": {
        "file": "requirements.txt",
        "line": 14,
        "column": null,
        "end_line": null,
        "snippet": "python-jwt-utils==1.0.0"
      },
      "suggestion": "Remove 'python-jwt-utils' and find the correct package name.",
      "metadata": {}
    }
  ],
  "summary": {
    "files_scanned": 42,
    "total_findings": 2,
    "duration_seconds": 1.2,
    "analyzers_run": ["dependency", "auth"],
    "by_severity": {
      "critical": 1,
      "high": 1
    },
    "by_category": {
      "dependency": 1,
      "auth": 1
    },
    "by_rule": {
      "DEP-001": 1,
      "AUTH-005": 1
    },
    "by_file": {
      "requirements.txt": 1,
      "src/main.py": 1
    },
    "has_blocking": true,
    "errors": []
  },
  "errors": []
}
```

### Campos

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `version` | string | Version de vigil |
| `files_scanned` | int | Numero de archivos analizados |
| `duration_seconds` | float | Duracion del scan en segundos |
| `analyzers_run` | array | Lista de analyzers ejecutados |
| `findings_count` | int | Numero total de findings |
| `findings` | array | Lista de findings (vacio si no hay problemas) |
| `summary` | object | Resumen estadistico (severidad, categoria, regla, archivos top 10) |
| `errors` | array | Errores de ejecucion de analyzers |

### Cada finding

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `rule_id` | string | ID unico de la regla (ej. `DEP-001`) |
| `category` | string | Categoria: `dependency`, `auth`, `secrets`, `test-quality` |
| `severity` | string | `critical`, `high`, `medium`, `low`, `info` |
| `message` | string | Descripcion del problema |
| `location` | object | Ubicacion en el codigo (incluye `snippet` solo si esta presente) |
| `suggestion` | string\|null | Sugerencia de correccion |
| `metadata` | object | Datos adicionales especificos de la regla |

### Uso tipico

```bash
# Generar y procesar con jq
vigil scan src/ -f json | jq '.findings[] | select(.severity == "critical")'

# Guardar a archivo
vigil scan src/ -f json -o report.json

# Integrar con scripts
vigil scan src/ -f json | python process_results.py
```

---

## JUnit XML

Formato compatible con dashboards de CI/CD (Jenkins, GitLab CI, Azure DevOps, etc.). Cada finding se representa como un test case fallido.

### Estructura

```xml
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="vigil" tests="2" failures="2" errors="0" time="1.200">
    <properties>
      <property name="vigil.version" value="0.6.0" />
      <property name="vigil.files_scanned" value="42" />
      <property name="vigil.analyzers" value="dependency,auth" />
    </properties>
    <testcase name="DEP-001: requirements.txt:14" classname="vigil.dependency">
      <failure type="error" message="Package 'python-jwt-utils' does not exist in pypi.">
Rule: DEP-001
Severity: critical
Category: dependency
File: requirements.txt:14
Suggestion: Remove 'python-jwt-utils' and find the correct package name.
Snippet: python-jwt-utils==1.0.0
      </failure>
    </testcase>
    <testcase name="AUTH-005: src/main.py:8" classname="vigil.auth">
      <failure type="error" message="CORS configured with '*' allowing requests from any origin.">
Rule: AUTH-005
Severity: high
Category: auth
File: src/main.py:8
Suggestion: Restrict CORS to specific trusted origins.
      </failure>
    </testcase>
  </testsuite>
</testsuites>
```

### Mapeo de severidad

| Severidad vigil | JUnit failure type |
|------------------|--------------------|
| CRITICAL | `error` |
| HIGH | `error` |
| MEDIUM | `warning` |
| LOW | `warning` |
| INFO | `warning` |

### Uso tipico

```bash
# Generar reporte JUnit
vigil scan src/ -f junit -o report.xml
```

En **GitLab CI**, el reporte se puede publicar como artifact de test:

```yaml
vigil:
  script:
    - vigil scan src/ -f junit -o report.xml
  artifacts:
    reports:
      junit: report.xml
```

En **Jenkins**, se puede usar con el plugin JUnit:

```groovy
stage('Security Scan') {
    steps {
        sh 'vigil scan src/ -f junit -o report.xml'
    }
    post {
        always {
            junit 'report.xml'
        }
    }
}
```

---

## SARIF 2.1.0

Static Analysis Results Interchange Format. Formato estandar de la industria para resultados de analisis estatico. Compatible con GitHub Code Scanning, VS Code SARIF Viewer, y otras plataformas.

### Estructura

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "vigil",
          "version": "0.6.0",
          "semanticVersion": "0.6.0",
          "informationUri": "https://github.com/org/vigil",
          "rules": [
            {
              "id": "DEP-001",
              "name": "HallucinatedDependency",
              "shortDescription": {
                "text": "Package declared as dependency does not exist in the public registry."
              },
              "defaultConfiguration": {
                "level": "error"
              },
              "helpUri": "https://github.com/org/vigil/docs/rules/DEP-001",
              "properties": {
                "cwe": "CWE-829",
                "owasp": "LLM03"
              }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "DEP-001",
          "ruleIndex": 0,
          "level": "error",
          "message": {
            "text": "Package 'python-jwt-utils' does not exist in pypi."
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "requirements.txt"
                },
                "region": {
                  "startLine": 14,
                  "snippet": {
                    "text": "python-jwt-utils==1.0.0"
                  }
                }
              }
            }
          ],
          "fixes": [
            {
              "description": {
                "text": "Remove 'python-jwt-utils' and find the correct package name."
              }
            }
          ]
        }
      ],
      "invocations": [
        {
          "executionSuccessful": true,
          "toolExecutionNotifications": []
        }
      ]
    }
  ]
}
```

### Mapeo de severidad

| Severidad vigil | SARIF level |
|------------------|-------------|
| CRITICAL | `error` |
| HIGH | `error` |
| MEDIUM | `warning` |
| LOW | `note` |
| INFO | `note` |

### Elementos SARIF

- **`tool.driver.rules`**: Solo incluye reglas que generaron findings (no las 26 reglas completas).
- **`tool.driver.semanticVersion`**: Version semantica de vigil.
- **`defaultConfiguration`**: Nivel por defecto de la regla (`error`, `warning`, `note`).
- **`helpUri`**: URL a la documentacion de la regla.
- **`ruleIndex`**: Indice numerico que referencia la posicion de la regla en `tool.driver.rules`.
- **`results`**: Cada finding como un resultado individual con ubicacion fisica.
- **`region.snippet`**: Fragmento de codigo, incluido si el finding tiene snippet.
- **`fixes`**: Si el finding tiene sugerencia, se incluye como `fixes[].description`.
- **`invocations`**: Estado de ejecucion y notificaciones de errores de analyzers.
- **`properties.cwe`**: Referencia CWE si la regla la tiene.
- **`properties.owasp`**: Referencia OWASP si la regla la tiene.

### Uso con GitHub Code Scanning

```bash
# Generar SARIF
vigil scan src/ -f sarif -o vigil.sarif
```

En GitHub Actions:

```yaml
- name: Run vigil
  run: vigil scan src/ -f sarif -o vigil.sarif
  continue-on-error: true

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: vigil.sarif
```

Los findings aparecen directamente en la pestana "Security" del repositorio y como anotaciones en los pull requests.

---

## Comparacion de formatos

| Caracteristica | Human | JSON | JUnit | SARIF |
|----------------|-------|------|-------|-------|
| Lectura terminal | Si | No | No | No |
| Procesamiento programatico | No | Si | Parcial | Si |
| Colores | Si (TTY) | No | No | No |
| GitHub Code Scanning | No | No | No | Si |
| CI dashboards | No | No | Si | Si |
| Sugerencias de fix | Si | Si | Si | Si |
| Referencias CWE | No | No | No | Si |
| Definicion de reglas | No | No | No | Si |

---

## Combinacion de formatos

Es posible generar multiples reportes en una sola ejecucion usando scripts:

```bash
# Generar JSON y SARIF en una pasada
vigil scan src/ -f json -o report.json
vigil scan src/ -f sarif -o vigil.sarif
vigil scan src/ -f junit -o report.xml
```

Dado que vigil usa cache para las respuestas de registries, las ejecuciones sucesivas son rapidas porque no repiten HTTP requests.
