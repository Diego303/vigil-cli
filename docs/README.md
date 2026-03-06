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
| [Analizadores](analizadores.md) | Referencia tecnica de los analyzers implementados (DependencyAnalyzer) |
| [Arquitectura](arquitectura.md) | Estructura interna, flujo del engine, protocolo de analyzers |
| [Buenas practicas](buenas-practicas.md) | Recomendaciones para equipos que usan agentes de IA para generar codigo |
| [Contribuir](contribuir.md) | Guia para contribuir al proyecto, setup de desarrollo y testing |

## Estado del proyecto

vigil esta en desarrollo activo. La version actual (v0.2.0) incluye:

- CLI completa con 5 subcomandos (`scan`, `deps`, `tests`, `init`, `rules`)
- Motor de analisis con soporte para multiples analyzers
- **Dependency Analyzer activo** — detecta paquetes alucinados, typosquatting, versiones inexistentes (DEP-001, DEP-002, DEP-003, DEP-005, DEP-007)
- 26 reglas definidas en 4 categorias
- 4 formatos de salida (human, JSON, JUnit XML, SARIF 2.1.0)
- Sistema de configuracion con YAML, presets y overrides por CLI
- 632 tests unitarios (~94% cobertura)

Los analyzers restantes (Auth, Secrets, Test Quality) se estan implementando progresivamente. Consulta el [SEGUIMIENTO-V0.md](../SEGUIMIENTO-V0.md) para el estado detallado.
