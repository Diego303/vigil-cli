# Seguridad

Este documento describe el modelo de amenazas de vigil, que detecta, como se alinea con estandares de la industria, y cuales son sus limitaciones.

## Problema que resuelve vigil

Los agentes de IA (Copilot, Cursor, Claude Code, ChatGPT, etc.) generan codigo que pasa revision humana superficial pero contiene patrones de seguridad peligrosos:

1. **Dependencias alucinadas (slopsquatting)**: El agente inventa nombres de paquetes que no existen. Un atacante registra ese nombre con codigo malicioso. Cuando alguien ejecuta `pip install` o `npm install`, instala el paquete del atacante.

2. **Patrones de auth inseguros**: Endpoints sin autenticacion, CORS abierto, JWT con secrets placeholder, cookies sin flags de seguridad.

3. **Secrets copiados de ejemplos**: El agente copia valores de `.env.example`, usa placeholders como "your-api-key-here", o genera secrets con entropia baja.

4. **Tests que no verifican nada**: Tests sin assertions, assertions triviales (`assert x is not None`), mocks que replican la implementacion.

Estos problemas son **especificos del codigo generado por IA** y no son detectados por herramientas SAST tradicionales (Semgrep, Bandit, ESLint) porque:

- Las herramientas SAST no verifican que los paquetes existan en registries.
- No detectan slopsquatting ni dependencias alucinadas.
- No evaluan la calidad real de los tests.
- No comparan valores con `.env.example`.

---

## Modelo de amenazas

### Actores de amenaza

| Actor | Motivacion | Vector |
|-------|------------|--------|
| Agente de IA | Genera codigo plausible pero inseguro | Alucinaciones, patrones copiados de ejemplos |
| Atacante de slopsquatting | Comprometer dependencias | Registrar nombres de paquetes alucinados |
| Atacante de typosquatting | Comprometer dependencias | Registrar nombres similares a paquetes populares |
| Desarrollador sin experiencia | Aceptar codigo del agente sin revision | Confianza excesiva en el output del agente |

### Superficie de ataque

1. **Supply chain (dependencias)**: El archivo de dependencias es la superficie de ataque mas critica. Un solo paquete malicioso puede comprometer todo el sistema.

2. **Codigo fuente**: Patrones de auth inseguros, secrets hardcodeados, configuraciones permisivas.

3. **Tests**: Cobertura falsa que da sensacion de seguridad sin verificar nada real.

### Flujo de ataque tipico

```
1. Desarrollador pide al agente de IA: "Crea una API REST con autenticacion JWT"
2. El agente genera codigo con:
   - Un paquete que no existe ("python-jwt-utils")
   - JWT secret hardcodeado ("supersecret123")
   - CORS con allow_origins=["*"]
   - Tests sin assertions reales
3. El desarrollador revisa superficialmente y aprueba el PR
4. Un atacante registra "python-jwt-utils" en PyPI con malware
5. En el siguiente `pip install`, se instala el paquete malicioso
```

vigil detecta los 4 problemas del paso 2. Desde v0.6.0, los cuatro analyzers estan activos: Dependency (DEP), Auth (AUTH), Secrets (SEC) y Test Quality (TEST).

---

## Alineacion con OWASP

vigil se alinea con el **OWASP Top 10 for LLM Applications (2025)**:

### LLM02 — Sensitive Information Disclosure

**Que cubre vigil:**
- SEC-001: Placeholder secrets en codigo
- SEC-002: Secrets con entropia baja
- SEC-003: Connection strings con credenciales
- SEC-004: Variables de entorno con defaults sensibles
- SEC-005: Archivos de secrets fuera de .gitignore
- SEC-006: Valores copiados de .env.example
- AUTH-004: JWT secrets hardcodeados

**Conexion con LLMs:** Los agentes de IA frecuentemente copian valores de ejemplo de la documentacion o generan secrets predecibles cuando un usuario pide "crea una configuracion de base de datos" o "genera un token JWT".

### LLM03 — Supply Chain Vulnerabilities

**Que cubre vigil:**
- DEP-001: Dependencias alucinadas (slopsquatting)
- DEP-002: Dependencias sospechosamente nuevas
- DEP-003: Typosquatting
- DEP-004: Dependencias impopulares
- DEP-005: Dependencias sin repositorio fuente
- DEP-006: Imports sin declarar en dependencias
- DEP-007: Versiones inexistentes

**Conexion con LLMs:** Esta es la contribucion principal de vigil. Los LLMs generan nombres de paquetes que suenan plausibles pero no existen ("python-jwt-utils", "fast-json-parser", "express-auth-middleware"). Ningun otro scanner verifica esto.

### LLM06 — Excessive Agency

**Que cubre vigil:**
- AUTH-001: Endpoints sensibles sin autenticacion
- AUTH-002: Endpoints destructivos sin autorizacion
- AUTH-005: CORS permisivo
- AUTH-006: Cookies sin flags de seguridad

**Conexion con LLMs:** Los agentes de IA generan endpoints funcionales pero sin los controles de acceso necesarios. Cuando un agente crea un endpoint DELETE, rara vez agrega verificacion de autorizacion.

---

## Referencias CWE

vigil mapea sus reglas a Common Weakness Enumerations (CWE) cuando aplica:

| CWE | Nombre | Reglas vigil |
|-----|--------|-------------|
| CWE-306 | Missing Authentication for Critical Function | AUTH-001 |
| CWE-208 | Observable Timing Discrepancy | AUTH-007 |
| CWE-614 | Sensitive Cookie Without 'Secure' | AUTH-006 |
| CWE-798 | Hard-coded Credentials | AUTH-004, SEC-001, SEC-002, SEC-003 |
| CWE-829 | Inclusion of Untrusted Functionality | DEP-001, DEP-003 |
| CWE-862 | Missing Authorization | AUTH-002 |
| CWE-942 | Permissive Cross-domain Policy | AUTH-005 |

Las referencias CWE se incluyen en los reportes SARIF para integracion con plataformas de seguridad que usan CWE como taxonomia.

---

## Lo que vigil NO es

Es importante entender las limitaciones de vigil:

### vigil no reemplaza a:

| Herramienta | Proposito | Complementariedad |
|-------------|-----------|-------------------|
| **Semgrep/Bandit** | SAST generalista | vigil complementa con checks especificos de IA |
| **Snyk/Dependabot** | Vulnerabilidades conocidas (CVE) | vigil detecta paquetes que NO existen, Snyk detecta vulnerabilidades en paquetes que SI existen |
| **Gitleaks/TruffleHog** | Deteccion de secrets reales (API keys, tokens) | vigil detecta placeholders y secrets de baja entropia |
| **SonarQube** | Calidad de codigo general | vigil se enfoca en patrones especificos de IA |

### vigil no detecta:

- **Vulnerabilidades CVE conocidas**: Para eso usar Snyk, Dependabot, o `pip-audit`.
- **Inyeccion SQL/XSS generica**: Para eso usar Semgrep o Bandit.
- **Secrets reales filtrados**: Para eso usar Gitleaks o TruffleHog.
- **Vulnerabilidades en codigo compilado**: vigil solo analiza codigo fuente.
- **Problemas de logica de negocio**: vigil busca patrones, no entiende logica.
- **Codigo en lenguajes no soportados**: Actualmente solo Python y JavaScript/TypeScript.

### vigil no usa IA

vigil es **determinista**. No usa LLMs, modelos de machine learning, ni heuristicas estadisticas. Cada regla es un patron definido con logica explicita. Esto tiene ventajas e inconvenientes:

**Ventajas:**
- Resultados reproducibles: el mismo codigo siempre produce los mismos findings.
- Sin falsos positivos aleatorios.
- Sin dependencia de APIs externas de IA.
- Rapido: no hay latencia de inferencia.
- Auditable: cada regla es inspeccionable.

**Inconvenientes:**
- No puede detectar problemas novedosos que no se anticiparon en las reglas.
- Menos flexible que un modelo que "entiende" contexto.
- Los patrones deben actualizarse manualmente.

---

## Seguridad de vigil como herramienta

### HTTP requests

vigil hace HTTP requests a registries publicos (PyPI, npm) para verificar la existencia de paquetes. Estas requests:

- Solo son GET requests de lectura a las APIs publicas de PyPI (`pypi.org/pypi/{name}/json`) y npm (`registry.npmjs.org/{name}`).
- No envian datos del proyecto (excepto nombres de paquetes).
- Se pueden desactivar completamente con `--offline`.
- Se cachean localmente en `~/.cache/vigil/registry/` con TTL configurable (default 24h).
- Los errores de red **asumen que el paquete existe** para evitar falsos positivos en conexiones inestables.
- El cliente HTTP usa `httpx` con timeout de 10 segundos y reutiliza conexiones.

### Cache

El cache se almacena como archivos JSON individuales en el filesystem local:

- Ubicacion: `~/.cache/vigil/registry/`
- Contenido: metadata publica de paquetes (nombre, version, fecha de publicacion, descargas).
- TTL: 24 horas por defecto (configurable).
- No contiene datos sensibles del proyecto.

### Sin telemetria

vigil no envia telemetria, metricas, ni datos de uso a ningun servidor. Todo se ejecuta localmente.

### Dependencias de vigil

vigil depende de paquetes de confianza y bien establecidos:

| Paquete | Proposito | Descargas semanales |
|---------|-----------|---------------------|
| click | CLI framework | 50M+ |
| pydantic | Validacion de config | 40M+ |
| httpx | HTTP client | 20M+ |
| structlog | Logging estructurado | 5M+ |
| pyyaml | Parser YAML | 50M+ |

---

## Recomendaciones de seguridad

### Para equipos que usan agentes de IA

1. **Ejecutar vigil en CI**: Automatizar el scan en cada PR para que ningun codigo generado por IA llegue a produccion sin verificacion.

2. **No confiar en el agente para dependencias**: Siempre verificar manualmente que los paquetes sugeridos existan y sean los correctos.

3. **Revisar secrets generados**: Los agentes frecuentemente generan secrets placeholder. Asegurarse de que las variables de entorno se carguen de un `.env` real y no de valores por defecto.

4. **Verificar tests generados**: Los tests generados por IA tienden a ser superficiales. Usar `vigil tests` para detectar tests sin assertions reales.

5. **Configurar fail-on segun el entorno**: Usar `--fail-on critical` en desarrollo local y `--fail-on medium` en CI de produccion.

### Para administradores de seguridad

1. **Usar formato SARIF**: Integrar vigil con GitHub Code Scanning o plataformas de seguridad que soporten SARIF.

2. **Combinar con otras herramientas**: vigil complementa pero no reemplaza SAST, SCA, y secret scanning. Un pipeline completo incluye:
   - vigil (patrones especificos de IA)
   - Semgrep/Bandit (SAST generalista)
   - Snyk/Dependabot (CVEs en dependencias)
   - Gitleaks (secrets reales filtrados)

3. **Auditar el cache periodicamente**: Limpiar `~/.cache/vigil/registry/` si se sospecha de datos corruptos o stale.

4. **Usar estrategia strict para compliance**: La estrategia `strict` alinea los thresholds con requisitos de SOC 2, ISO 27001, y EU CRA.
