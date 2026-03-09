# Docker

vigil puede ejecutarse dentro de contenedores Docker para entornos reproducibles, pipelines de CI, o integracion en workflows existentes basados en Docker.

## Imagen base recomendada

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir vigil-ai-cli

WORKDIR /app
ENTRYPOINT ["vigil"]
CMD ["--help"]
```

### Build

```bash
docker build -t vigil .
```

### Uso

```bash
# Escanear un directorio local
docker run --rm -v $(pwd):/app vigil scan src/

# Con formato JSON
docker run --rm -v $(pwd):/app vigil scan src/ -f json

# Con archivo de config
docker run --rm -v $(pwd):/app vigil scan src/ -c .vigil.yaml

# Guardar reporte
docker run --rm -v $(pwd):/app vigil scan src/ -f sarif -o vigil.sarif
```

---

## Dockerfile de produccion

Un Dockerfile mas robusto para uso en produccion o distribucion:

```dockerfile
FROM python:3.12-slim AS base

# Metadata
LABEL maintainer="vigil team"
LABEL description="Security scanner for AI-generated code"
LABEL version="1.0.0"

# Crear usuario no-root
RUN groupadd -r vigil && useradd -r -g vigil vigil

# Instalar vigil
RUN pip install --no-cache-dir vigil-ai-cli

# Directorio de trabajo
WORKDIR /scan

# Directorio de cache
RUN mkdir -p /home/vigil/.cache/vigil/registry && \
    chown -R vigil:vigil /home/vigil

# Cambiar a usuario no-root
USER vigil

ENTRYPOINT ["vigil"]
CMD ["scan", "."]
```

### Ventajas de esta configuracion

- **Usuario no-root**: Mejor practica de seguridad. vigil no necesita privilegios.
- **`--no-cache-dir`**: Reduce el tamano de la imagen.
- **`WORKDIR /scan`**: Punto de montaje claro para el codigo a escanear.
- **Cache directory**: Pre-creado con permisos correctos.

---

## Uso con Docker Compose

Para integracion en proyectos que usan Docker Compose:

```yaml
# docker-compose.yaml
services:
  vigil:
    build:
      context: .
      dockerfile: Dockerfile.vigil
    volumes:
      - .:/scan:ro
      - vigil-cache:/home/vigil/.cache/vigil
    command: scan src/ --fail-on high -f json -o /scan/vigil-report.json

volumes:
  vigil-cache:
```

El volumen `vigil-cache` persiste el cache del registry entre ejecuciones, evitando HTTP requests repetidas.

---

## Modo offline en Docker

Para runners sin acceso a internet o en redes restringidas:

```bash
docker run --rm -v $(pwd):/scan --network none vigil scan src/ --offline
```

`--network none` desactiva la red del contenedor, asegurando que no se hagan requests externas. Combinado con `--offline`, vigil ejecuta solo checks estaticos.

---

## Cache del registry

### Persistir cache entre ejecuciones

```bash
# Crear volumen para cache
docker volume create vigil-cache

# Usar el volumen
docker run --rm \
  -v $(pwd):/scan \
  -v vigil-cache:/home/vigil/.cache/vigil \
  vigil scan src/
```

### Pre-calentar cache

Si quieres pre-cargar el cache antes de un scan offline:

```bash
# Primera ejecucion: con red, para llenar cache
docker run --rm \
  -v $(pwd):/scan \
  -v vigil-cache:/home/vigil/.cache/vigil \
  vigil deps

# Ejecuciones siguientes: sin red, usando cache
docker run --rm \
  -v $(pwd):/scan \
  -v vigil-cache:/home/vigil/.cache/vigil \
  --network none \
  vigil scan src/
```

---

## CI con Docker

### GitHub Actions con Docker

```yaml
jobs:
  vigil:
    runs-on: ubuntu-latest
    container:
      image: python:3.12-slim
    steps:
      - uses: actions/checkout@v4
      - run: pip install vigil-ai-cli
      - run: vigil scan src/ --fail-on high
```

### GitLab CI con Docker

```yaml
vigil:
  image: python:3.12-slim
  stage: test
  script:
    - pip install vigil-ai-cli
    - vigil scan src/ -f junit -o report.xml
  artifacts:
    reports:
      junit: report.xml
```

### Con imagen custom pre-built

Para evitar instalar vigil en cada ejecucion:

```yaml
# GitLab CI
vigil:
  image: registry.example.com/tools/vigil:latest
  stage: test
  script:
    - vigil scan src/ --fail-on high
```

---

## Multi-stage build

Si vigil forma parte de un pipeline de build mas grande:

```dockerfile
# Stage 1: Security scan
FROM python:3.12-slim AS security
RUN pip install --no-cache-dir vigil-ai-cli
WORKDIR /app
COPY . .
RUN vigil scan src/ --fail-on high

# Stage 2: Build real de la app
FROM python:3.12-slim AS production
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "-m", "app"]
```

Si vigil encuentra problemas (exit code 1), el build falla en el primer stage y no se construye la imagen de produccion. Esto actua como un quality gate en el proceso de build.

---

## Tamano de imagen

Estimaciones del tamano de imagen:

| Base | Tamano aprox. |
|------|---------------|
| `python:3.12-slim` + vigil | ~180 MB |
| `python:3.12-alpine` + vigil | ~120 MB |
| `python:3.12` + vigil | ~1 GB |

Se recomienda usar `python:3.12-slim` como balance entre tamano y compatibilidad. Alpine puede causar problemas con algunas dependencias compiladas.

---

## Buenas practicas

1. **Montar el codigo como read-only** (`-v $(pwd):/scan:ro`): vigil no modifica archivos. El montaje read-only previene escrituras accidentales.

2. **Persistir el cache del registry**: Usar un volumen Docker o un directorio del host para evitar HTTP requests repetidas entre ejecuciones.

3. **Usar usuario no-root**: vigil no necesita privilegios elevados.

4. **Pinear la version de vigil**: En Dockerfiles de produccion, usar `pip install vigil-ai-cli==1.0.0` en lugar de `vigil-ai-cli` para builds reproducibles.

5. **Separar scan de build**: En multi-stage builds, ejecutar vigil como un stage independiente para que falle rapido sin desperdiciar recursos en stages posteriores.

6. **Output a archivos dentro del volumen**: Cuando se usa `--output`, asegurarse de que el archivo de salida este en un directorio montado para poder acceder al reporte fuera del contenedor.
