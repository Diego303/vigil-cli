# Buenas practicas

Recomendaciones para equipos que usan agentes de IA para generar codigo y quieren mantener estandares de seguridad.

## Regla general

> **Nunca confies ciegamente en el output de un agente de IA.** Trata el codigo generado con el mismo escrutinio que tratarias un pull request de un desarrollador junior que no conoce tu stack.

---

## Dependencias

### Verificar antes de instalar

Antes de ejecutar `pip install` o `npm install` con dependencias sugeridas por un agente:

1. **Buscar el paquete manualmente** en [pypi.org](https://pypi.org) o [npmjs.com](https://npmjs.com).
2. **Verificar el nombre exacto**: Los agentes frecuentemente inventan nombres plausibles que no existen.
3. **Revisar la antiguedad**: Desconfiar de paquetes creados en los ultimos 30 dias.
4. **Revisar las descargas**: Paquetes con menos de 100 descargas semanales merecen escrutinio extra.
5. **Buscar el repositorio fuente**: Paquetes sin repositorio vinculado son sospechosos.

### Ejecutar vigil deps antes de instalar

```bash
# Verificar dependencias ANTES de instalar
vigil deps

# Si hay findings criticos, corregir primero
vigil deps -f json | jq '.findings[] | select(.severity == "critical")'
```

### Mantener un lockfile

Los lockfiles (`package-lock.json`, `poetry.lock`, `pip-tools` con `requirements.txt` generado) anclan versiones exactas y hashes. Esto previene que un paquete se modifique entre ejecuciones.

### No aceptar versiones inventadas

Los agentes a veces sugieren versiones que no existen:

```
# Esto puede ser inventado por el agente
flask==99.0.0
```

vigil detecta esto con la regla DEP-007, pero es buena practica verificar manualmente las versiones.

---

## Autenticacion y autorizacion

### Siempre agregar auth middleware

Cuando un agente genera endpoints, **siempre** agregar autenticacion explicitamente. Los agentes tienden a generar endpoints funcionales pero sin proteccion.

**Mal (generado por agente):**
```python
@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    db.delete_user(user_id)
    return {"deleted": user_id}
```

**Bien (corregido):**
```python
@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(403)
    db.delete_user(user_id)
    return {"deleted": user_id}
```

### CORS: restringir origenes

**Nunca** aceptar CORS con `*` en produccion:

```python
# MAL
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# BIEN
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://miapp.com", "https://admin.miapp.com"],
)
```

### JWT: generar secrets reales

```python
# MAL
SECRET_KEY = "supersecret123"

# BIEN
import secrets
# Generar una vez y almacenar en variable de entorno
SECRET_KEY = os.environ["JWT_SECRET_KEY"]
# Para generar: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Cookies: activar todos los flags

```python
response.set_cookie(
    "session",
    value=token,
    httponly=True,     # No accesible desde JavaScript
    secure=True,       # Solo enviar via HTTPS
    samesite="lax",    # Proteccion CSRF
    max_age=3600,      # Expiracion
)
```

---

## Secrets y credenciales

### Nunca hardcodear secrets

Aunque el agente sugiera valores por defecto "temporales":

```python
# MAL — el agente lo genera asi
DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-not-for-production")

# BIEN — sin defaults inseguros
DATABASE_URL = os.environ["DATABASE_URL"]  # Falla si no esta definida
SECRET_KEY = os.environ["SECRET_KEY"]
```

### Usar .env con .gitignore

1. Crear `.env.example` con **placeholders** (no valores reales):
   ```
   DATABASE_URL=postgresql://user:password@host:5432/dbname
   SECRET_KEY=generate-with-secrets-module
   ```

2. Crear `.env` con valores reales (nunca commitear).

3. Agregar a `.gitignore`:
   ```
   .env
   .env.local
   .env.production
   *.pem
   *.key
   credentials.json
   ```

### Verificar con vigil

```bash
# Detecta secrets placeholder, entropia baja, y valores copiados de .env.example
vigil scan src/ -C secrets
```

---

## Tests

### Exigir assertions reales

Un test sin assertions no es un test:

```python
# MAL — solo verifica que no crash
def test_login():
    response = client.post("/login", json={"user": "admin", "pass": "123"})

# BIEN — verifica comportamiento
def test_login():
    response = client.post("/login", json={"user": "admin", "pass": "123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
```

### Verificar status codes en tests de API

```python
# MAL — no verifica si la request fallo
def test_get_users():
    response = client.get("/users")
    users = response.json()
    assert len(users) > 0

# BIEN
def test_get_users():
    response = client.get("/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) > 0
```

### No capturar excepciones genericas en tests

```python
# MAL — oculta errores reales
def test_complex_operation():
    try:
        result = complex_operation()
    except Exception:
        pass  # El test nunca falla

# BIEN — dejar que la excepcion propague
def test_complex_operation():
    result = complex_operation()
    assert result.status == "success"
```

### Evitar mocks circulares

```python
# MAL — el mock retorna exactamente lo que el test espera
def test_calculate():
    with patch("app.calculate") as mock:
        mock.return_value = 42
        result = app.calculate(6, 7)
        assert result == 42  # No se testo nada real

# BIEN — mockear la dependencia, no la funcion bajo test
def test_calculate():
    with patch("app.database.get_multiplier") as mock:
        mock.return_value = 2
        result = app.calculate(6, 7)
        assert result == 26  # 6 * 7 / 2 — logica real testeada
```

### Ejecutar vigil tests regularmente

```bash
# Detectar tests sin assertions, triviales, y mocks circulares
vigil tests

# Requerir al menos 2 assertions por test
vigil tests --min-assertions 2
```

---

## Workflow recomendado

### Para desarrolladores individuales

1. **Pre-commit hook**: `vigil scan --changed-only --fail-on critical --quiet`
2. **Antes de PR**: `vigil scan src/ --fail-on high`
3. **Revision manual**: Leer cada finding y corregir.

### Para equipos

1. **Config compartida**: Commitear `.vigil.yaml` con la config del equipo.
2. **CI obligatorio**: vigil en el pipeline de PR con `--fail-on high`.
3. **Produccion estricta**: Config `strict` para releases.
4. **Documentar excepciones**: Si se desactiva una regla, documentar por que en la config.

```yaml
# .vigil.yaml
rules:
  # Desactivado porque usamos tokens de larga duracion para webhooks
  # Aprobado por: @security-team en PR #123
  AUTH-003:
    enabled: false
```

### Escalamiento progresivo

| Semana | fail-on | Reglas activas | Objetivo |
|--------|---------|----------------|----------|
| 1 | critical | DEP-001, DEP-007, SEC-001-003 | Solo lo mas grave |
| 2 | high | + AUTH-001, AUTH-002, AUTH-005 | Agregar auth |
| 3 | high | + TEST-001, SEC-004-006 | Agregar tests y secrets |
| 4 | medium | Todas | Cobertura completa |

---

## Prompts mejorados para agentes

Cuando uses un agente de IA, incluir instrucciones de seguridad en el prompt:

### Para dependencias

> "Genera el codigo usando solo paquetes que existan en PyPI. Verifica que los nombres sean correctos. No inventes paquetes."

### Para autenticacion

> "Todos los endpoints deben tener autenticacion. Usa Depends(get_current_user) en FastAPI. Los endpoints DELETE y PUT requieren autorizacion explicita."

### Para secrets

> "No hardcodees secrets ni valores por defecto. Todas las configuraciones sensibles deben leerse de variables de entorno sin valor por defecto."

### Para tests

> "Cada test debe tener al menos 2 assertions significativas. No uses assert is not None como unica assertion. Siempre verifica el status code en tests de API."

---

## Checklist de revision de codigo generado por IA

Antes de aprobar un PR con codigo generado por IA:

- [ ] Ejecutar `vigil scan` y corregir todos los findings.
- [ ] Verificar que todas las dependencias existen en el registry.
- [ ] Confirmar que no hay secrets hardcodeados.
- [ ] Verificar que los endpoints tienen auth middleware.
- [ ] Confirmar que CORS esta restringido a origenes especificos.
- [ ] Verificar que los tests tienen assertions significativas.
- [ ] Revisar que `.env` esta en `.gitignore`.
- [ ] Confirmar que no hay valores copiados de `.env.example`.
