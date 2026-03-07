# Compliance y uso empresarial

Este documento describe como vigil se alinea con frameworks de compliance y como integrarlo en entornos empresariales que usan agentes de IA para generar codigo.

---

## Por que vigil en un entorno empresarial

Las organizaciones que adoptan agentes de IA (Copilot, Cursor, Claude Code, ChatGPT) para generar codigo enfrentan riesgos nuevos que las herramientas SAST tradicionales no cubren:

1. **Supply chain via alucinaciones**: Los agentes inventan nombres de paquetes. Un atacante puede registrar ese nombre con malware.
2. **Secrets de ejemplo en produccion**: Los agentes copian valores de documentacion (`"your-api-key-here"`) que terminan en produccion.
3. **Auth sin controles**: Los agentes generan endpoints funcionales pero sin middleware de autenticacion.
4. **Tests cosmeticos**: Los agentes generan tests que pasan pero no verifican nada real.

vigil detecta estos 4 patrones de forma **determinista, auditable y sin dependencia de APIs externas de IA**.

---

## Alineacion con frameworks de compliance

### OWASP Top 10 for LLM Applications (2025)

vigil se alinea directamente con 3 categorias del OWASP Top 10 for LLM Applications:

| OWASP Category | Reglas vigil | Cobertura |
|----------------|-------------|-----------|
| **LLM02** — Sensitive Information Disclosure | SEC-001, SEC-002, SEC-003, SEC-004, SEC-006, AUTH-004 | Detecta secrets hardcodeados, placeholders, connection strings con credenciales |
| **LLM03** — Supply Chain Vulnerabilities | DEP-001, DEP-002, DEP-003, DEP-005, DEP-007 | Detecta dependencias alucinadas, typosquatting, paquetes nuevos sospechosos |
| **LLM06** — Excessive Agency | AUTH-001, AUTH-002, AUTH-005, AUTH-006 | Detecta endpoints sin auth, CORS permisivo, cookies inseguras |

### EU Cyber Resilience Act (CRA)

El CRA exige que los productos con componentes digitales sean seguros "by design". vigil contribuye a:

| Requisito CRA | Como contribuye vigil |
|---------------|----------------------|
| Gestion de vulnerabilidades en componentes de terceros | DEP-001 a DEP-007 verifican que las dependencias existen, son legitimas y no son typosquatting |
| Proteccion de datos almacenados y en transito | SEC-001 a SEC-006 detectan credenciales hardcodeadas que comprometen datos |
| Control de acceso adecuado | AUTH-001 a AUTH-007 detectan endpoints sin autenticacion y configuraciones permisivas |
| Testing adecuado | TEST-001 a TEST-006 detectan tests que no verifican nada (desde v0.5.0) |

### SOC 2 Type II

| Trust Service Criteria | Reglas vigil relevantes |
|------------------------|------------------------|
| **CC6.1** — Logical access controls | AUTH-001, AUTH-002, AUTH-005, AUTH-006 |
| **CC6.6** — External threats | DEP-001, DEP-002, DEP-003 (supply chain) |
| **CC6.7** — Credential management | AUTH-004, SEC-001, SEC-002, SEC-003, SEC-004, SEC-006 |
| **CC7.1** — Vulnerability management | Todas las reglas DEP- para supply chain |

### ISO 27001:2022

| Control | Reglas vigil relevantes |
|---------|------------------------|
| **A.8.25** — Secure development lifecycle | Integrar vigil en CI/CD como quality gate |
| **A.8.26** — Application security requirements | AUTH-001 a AUTH-007 verifican controles de acceso |
| **A.8.28** — Secure coding | SEC-001 a SEC-006 detectan secrets en codigo |

### NIST Cybersecurity Framework (CSF) 2.0

| Function | Category | Reglas vigil |
|----------|----------|-------------|
| **Identify** | Asset Management | DEP-001 a DEP-007 (inventario de dependencias) |
| **Protect** | Access Control | AUTH-001 a AUTH-007 |
| **Protect** | Data Security | SEC-001 a SEC-006 |
| **Detect** | Continuous Monitoring | Integrar vigil en CI/CD pipelines |

---

## Integracion en pipelines empresariales

### Pipeline recomendado

```
Codigo generado por IA
    |
    v
[1. vigil scan]          <- Detecta patrones especificos de IA
    |
    v
[2. Semgrep/Bandit]      <- SAST generalista
    |
    v
[3. Snyk/Dependabot]     <- CVEs en dependencias
    |
    v
[4. Gitleaks]            <- Secrets reales filtrados
    |
    v
[5. Tests + Coverage]    <- Calidad funcional
    |
    v
Deploy
```

vigil complementa (no reemplaza) las herramientas existentes. Su valor unico esta en detectar problemas **especificos del codigo generado por IA**.

### Estrategia por entorno

| Entorno | Estrategia | `--fail-on` | Notas |
|---------|-----------|-------------|-------|
| Desarrollo local | `relaxed` | `critical` | Feedback rapido sin bloquear |
| CI/CD (feature branch) | `standard` | `high` | Balance entre velocidad y seguridad |
| CI/CD (main/release) | `strict` | `medium` | Maximo rigor antes de produccion |
| Auditoria de seguridad | `strict` | `low` | Reporte completo para analisis |

### Ejemplo GitHub Actions (produccion)

```yaml
- name: Security scan (AI-specific)
  run: |
    pip install vigil-ai-cli
    vigil scan src/ \
      --format sarif \
      --output results/vigil.sarif \
      --fail-on medium \
      --config .vigil.strict.yaml

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results/vigil.sarif
```

### Formato SARIF para plataformas de seguridad

vigil produce reportes en SARIF 2.1.0, compatible con:

- GitHub Code Scanning (nativo)
- GitLab Security Dashboard
- Azure DevOps
- SonarQube (via importador)
- Defect Dojo
- Snyk (via importador SARIF)

Cada finding incluye `ruleId`, `level`, `location`, y opcionalmente `fixes` con sugerencias de correccion.

---

## Reportes para auditorias

### Generar reporte JSON completo

```bash
vigil scan src/ --format json --output audit-report.json
```

El reporte JSON incluye:
- `findings`: Lista completa de hallazgos con rule_id, severity, message, location, suggestion
- `findings_count`: Total de hallazgos
- `files_scanned`: Archivos analizados
- `duration_seconds`: Tiempo de ejecucion
- `analyzers_run`: Analyzers ejecutados
- `errors`: Errores durante el analisis (si hubo)
- `version`: Version de vigil usada

### Generar reporte SARIF con referencias CWE

```bash
vigil scan src/ --format sarif --output audit-report.sarif
```

El reporte SARIF mapea cada regla a CWEs cuando aplica:

| CWE | Nombre | Reglas vigil |
|-----|--------|-------------|
| CWE-306 | Missing Authentication for Critical Function | AUTH-001 |
| CWE-208 | Observable Timing Discrepancy | AUTH-007 |
| CWE-614 | Sensitive Cookie Without 'Secure' | AUTH-006 |
| CWE-798 | Hard-coded Credentials | AUTH-004, SEC-001, SEC-002, SEC-003 |
| CWE-829 | Inclusion of Untrusted Functionality | DEP-001, DEP-003 |
| CWE-862 | Missing Authorization | AUTH-002 |
| CWE-942 | Permissive Cross-domain Policy | AUTH-005 |

---

## Privacidad y seguridad de vigil

vigil esta disenado para ser seguro en entornos empresariales:

- **Sin telemetria**: No envia datos a servidores externos.
- **Determinista**: No usa IA, ML, ni APIs externas de inferencia.
- **HTTP limitado**: Solo hace GET requests a APIs publicas de PyPI/npm para verificar existencia de paquetes. Se deshabilita con `--offline`.
- **Cache local**: Las respuestas de registries se cachean en `~/.cache/vigil/registry/` (no contienen datos del proyecto).
- **Auditable**: Cada regla es un patron definido en codigo. Sin cajas negras.
- **Sin side effects**: vigil solo lee archivos. Nunca modifica codigo, envia mensajes, ni crea recursos.

### Modo air-gapped

Para entornos sin acceso a internet:

```bash
vigil scan src/ --offline
```

En modo offline, solo se ejecutan checks estaticos (typosquatting por similaridad, auth patterns, secrets). Las reglas que requieren verificar registries (DEP-001, DEP-002, DEP-005, DEP-007) se omiten automaticamente.

---

## FAQ empresarial

### vigil reemplaza a Semgrep/Snyk/SonarQube?

No. vigil detecta patrones **especificos del codigo generado por IA** que otras herramientas no cubren. Es complementario:

| Problema | vigil | Semgrep | Snyk | Gitleaks |
|----------|-------|---------|------|----------|
| Paquete alucinado (no existe) | Si | No | No | No |
| Typosquatting | Si | No | Parcial | No |
| Placeholder secret (`"changeme"`) | Si | Parcial | No | No |
| Secret real filtrado | No | No | No | Si |
| CVE conocida en dependencia | No | No | Si | No |
| SQL injection | No | Si | No | No |

### Cuanto tarda un scan?

vigil es rapido porque no hace inferencia de IA. Un scan tipico:
- 100 archivos: < 1 segundo (offline), < 5 segundos (con verificacion de registries)
- 1000 archivos: < 5 segundos (offline), < 30 segundos (con cache frio)

### Se puede usar en monorepos?

Si. vigil soporta multiples paths y el descubrimiento de archivos hace pruning automatico de directorios como `node_modules/`, `.venv/`, etc.

```bash
vigil scan services/auth/ services/api/ libs/shared/
```

### Como excluir falsos positivos?

Dos opciones:

1. **Deshabilitar la regla** para todo el proyecto:
```yaml
rules:
  AUTH-005:
    enabled: false
```

2. **Cambiar la severidad** para que no bloquee:
```yaml
rules:
  AUTH-005:
    severity: "low"
```
