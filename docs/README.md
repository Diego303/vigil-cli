# Documentacion de vigil

Bienvenido a la documentacion de **vigil**, el scanner de seguridad para codigo generado por IA.

## Indice

| Documento | Descripcion |
|-----------|-------------|
| [Inicio rapido](inicio-rapido.md) | Instalacion, primer scan y conceptos basicos |
| [Referencia CLI](cli.md) | Todos los comandos, flags y opciones disponibles |
| [Configuracion](configuracion.md) | Archivo `.vigil.yaml`, estrategias, overrides y merge de config |
| [Reglas](reglas.md) | Catalogo completo de las 26 reglas con ejemplos de codigo vulnerable |
| [Formatos de salida](formatos-salida.md) | Human, JSON, JUnit XML y SARIF 2.1.0 |
| [Integracion CI/CD](ci-cd.md) | GitHub Actions, GitLab CI, pre-commit hooks y quality gates |
| [Docker](docker.md) | Uso en contenedores, Dockerfile de referencia y buenas practicas |
| [Seguridad](seguridad.md) | Modelo de amenazas, que detecta vigil, alineacion OWASP y limitaciones |
| [Analizadores](analizadores.md) | Referencia tecnica de los analyzers implementados (Dependency, Auth, Secrets, Test Quality) |
| [Arquitectura](arquitectura.md) | Estructura interna, flujo del engine, protocolo de analyzers |
| [Buenas practicas](buenas-practicas.md) | Recomendaciones para equipos que usan agentes de IA para generar codigo |
| [Compliance y uso empresarial](compliance.md) | Alineacion con OWASP, CRA, SOC 2, ISO 27001, NIST y uso en pipelines empresariales |
| [FAQ y Troubleshooting](faq.md) | Preguntas frecuentes, falsos positivos, rendimiento, encoding y problemas comunes |
| [Contribuir](contribuir.md) | Guia para contribuir al proyecto, setup de desarrollo y testing |

## Estado del proyecto

La version actual es **v1.0.0** (stable release). Incluye:

- CLI completa con 5 subcomandos (`scan`, `deps`, `tests`, `init`, `rules`)
- Motor de analisis con soporte para multiples analyzers
- **Dependency Analyzer activo** — detecta paquetes alucinados, typosquatting, versiones inexistentes (DEP-001, DEP-002, DEP-003, DEP-005, DEP-007)
- **Auth Analyzer activo** — detecta endpoints sin auth, CORS permisivo, JWT inseguro, cookies sin flags, timing attacks (AUTH-001 a AUTH-007)
- **Secrets Analyzer activo** — detecta placeholders, secrets de baja entropia, connection strings, env defaults, valores copiados de .env.example (SEC-001 a SEC-004, SEC-006)
- **Test Quality Analyzer activo** — detecta tests sin assertions, assertions triviales, catch-all exceptions, skips sin razon, API tests sin status code, mock mirrors (TEST-001 a TEST-006)
- **Corpus de paquetes populares** — 5000 PyPI + 3454 npm paquetes para deteccion de typosquatting con datos reales de descargas semanales
- 26 reglas definidas en 4 categorias (24 implementadas, 2 pendientes)
- 4 formatos de salida (human, JSON, JUnit XML, SARIF 2.1.0)
- Sistema de configuracion con YAML, presets y overrides por CLI
- Suite de integracion end-to-end con fixtures de codigo AI-generated real
- QA exhaustivo: 164 pruebas manuales + 10 bugs corregidos en V1 QA
- 1706 tests, 97% cobertura global

Consulta el [SEGUIMIENTO-V1.md](../SEGUIMIENTO-V1.md) para el estado actual y backlog.
