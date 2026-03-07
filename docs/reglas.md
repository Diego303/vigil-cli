# Catalogo de reglas

vigil V0 incluye 26 reglas en 4 categorias. Cada regla tiene un ID unico, severidad por defecto, y referencias a estandares de seguridad cuando aplica.

Para listar todas las reglas desde la terminal:

```bash
vigil rules
```

---

## CAT-01: Dependency Hallucination

> **Estado: IMPLEMENTADO** — El `DependencyAnalyzer` esta activo. Las reglas DEP-001, DEP-002, DEP-003, DEP-005 y DEP-007 estan implementadas. DEP-004 y DEP-006 estan diferidas para una version futura.

Detecta dependencias alucinadas (slopsquatting), typosquatting y paquetes sospechosos. Este es el diferenciador principal de vigil — ningun otro scanner verifica que las dependencias realmente existen.

### DEP-001 — Hallucinated dependency

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |
| OWASP | LLM03 — Supply Chain Vulnerabilities |
| CWE | CWE-829 — Inclusion of Functionality from Untrusted Control Sphere |

**Que detecta:** Un paquete declarado como dependencia no existe en el registry publico (PyPI o npm).

**Por que es critico:** Los LLMs frecuentemente generan nombres de paquetes que suenan plausibles pero no existen. Un atacante puede registrar ese nombre con codigo malicioso (slopsquatting). Cuando alguien ejecuta `pip install` o `npm install`, instala el paquete malicioso.

**Ejemplo de codigo vulnerable:**

```
# requirements.txt
flask==3.0.0
python-jwt-utils==1.0.0    # Este paquete NO existe en PyPI
requests==2.31.0
```

**Como corregirlo:** Buscar en PyPI/npm el paquete correcto. En este caso, probablemente el agente queria `PyJWT` o `python-jose`.

---

### DEP-002 — Suspiciously new dependency

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| OWASP | LLM03 |

**Que detecta:** El paquete existe pero fue publicado hace menos de 30 dias (configurable con `deps.min_age_days`).

**Por que importa:** Los paquetes nuevos no han tenido tiempo de ser auditados por la comunidad. Podrian ser paquetes maliciosos registrados como parte de un ataque de slopsquatting.

**Ejemplo:** Un paquete creado hace 3 dias con un nombre que suena util (`fast-json-parser`) pero que nadie ha revisado.

**Como corregirlo:** Verificar manualmente el paquete: revisar el codigo fuente, el maintainer, el proposito. Si es legitimo, agregar una excepcion en la config.

---

### DEP-003 — Typosquatting candidate

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| OWASP | LLM03 |
| CWE | CWE-829 |

**Que detecta:** El nombre del paquete es muy similar a un paquete popular (distancia de Levenshtein normalizada >= 0.85).

**Ejemplo de codigo vulnerable:**

```
# requirements.txt
reqeusts==2.31.0     # Typo de "requests"
```

**Como corregirlo:** Verificar el nombre correcto del paquete. En la sugerencia vigil indica el paquete popular al que se parece.

---

### DEP-004 — Unpopular dependency (pendiente)

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |
| Estado | **Diferida** — requiere API de estadisticas de descargas |

**Que detecta:** El paquete tiene menos de 100 descargas semanales (configurable con `deps.min_weekly_downloads`).

**Por que importa:** Los paquetes con muy pocas descargas pueden ser abandonados, tener vulnerabilidades no parchadas, o ser un indicador de un paquete falso.

---

### DEP-005 — No source repository

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |

**Que detecta:** El paquete no tiene un repositorio de codigo fuente vinculado en su metadata.

**Por que importa:** Sin acceso al codigo fuente, es imposible auditar que hace el paquete. Los paquetes legitimos casi siempre tienen un repositorio vinculado.

---

### DEP-006 — Missing dependency (pendiente)

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| Estado | **Diferida** — requiere parser de imports AST |

**Que detecta:** Un `import` en el codigo referencia un modulo que no esta declarado en las dependencias del proyecto.

**Ejemplo de codigo vulnerable:**

```python
# src/app.py
import magical_orm    # No esta en requirements.txt ni pyproject.toml

def get_users():
    return magical_orm.query("SELECT * FROM users")
```

---

### DEP-007 — Nonexistent version

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |

**Que detecta:** La version especificada del paquete no existe en el registry.

**Ejemplo de codigo vulnerable:**

```
# requirements.txt
flask==99.0.0        # Esta version no existe
```

---

## CAT-02: Auth & Permission Patterns

> **Estado: IMPLEMENTADO** — El `AuthAnalyzer` esta activo desde v0.3.0. Todas las reglas AUTH-001 a AUTH-007 estan implementadas. Soporta Python (FastAPI/Flask) y JavaScript (Express).

Detecta patrones de autenticacion y autorizacion inseguros que los agentes de IA generan con frecuencia.

### AUTH-001 — Unprotected sensitive endpoint

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| OWASP | LLM06 — Excessive Agency |
| CWE | CWE-306 — Missing Authentication for Critical Function |

**Que detecta:** Un endpoint que maneja datos sensibles (usuarios, pagos, admin) sin middleware de autenticacion.

**Ejemplo de codigo vulnerable (FastAPI):**

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):    # Sin Depends(get_current_user)
    return db.get_user(user_id)
```

---

### AUTH-002 — Destructive endpoint without authorization

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| CWE | CWE-862 — Missing Authorization |

**Que detecta:** Un endpoint DELETE o PUT sin verificacion de autorizacion.

**Ejemplo de codigo vulnerable:**

```python
@app.delete("/users/{user_id}")
async def delete_user(user_id: int):    # Cualquiera puede borrar usuarios
    db.delete_user(user_id)
    return {"deleted": user_id}
```

---

### AUTH-003 — Excessive token lifetime

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |

**Que detecta:** JWT con lifetime superior a 24 horas (configurable con `auth.max_token_lifetime_hours`).

**Ejemplo de codigo vulnerable:**

```python
token = jwt.encode(
    {"exp": datetime.utcnow() + timedelta(hours=72)},  # 72 horas
    SECRET_KEY
)
```

---

### AUTH-004 — Hardcoded JWT secret

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |
| CWE | CWE-798 — Use of Hard-coded Credentials |

**Que detecta:** JWT secret hardcodeado con un valor de placeholder o con entropia baja.

**Ejemplo de codigo vulnerable:**

```python
SECRET_KEY = "supersecret123"    # Hardcodeado y predecible
token = jwt.encode(payload, SECRET_KEY)
```

---

### AUTH-005 — CORS allow all origins

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| CWE | CWE-942 — Permissive Cross-domain Policy |

**Que detecta:** CORS configurado con `*` permitiendo requests desde cualquier origen.

**Ejemplo de codigo vulnerable:**

```python
# FastAPI
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Express
app.use(cors())    # Sin opciones = allow all
```

---

### AUTH-006 — Insecure cookie configuration

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |
| CWE | CWE-614 — Sensitive Cookie in HTTPS Session Without 'Secure' Attribute |

**Que detecta:** Cookies sin los flags de seguridad `httpOnly`, `secure`, o `sameSite`.

---

### AUTH-007 — Password comparison not timing-safe

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |
| CWE | CWE-208 — Observable Timing Discrepancy |

**Que detecta:** Comparacion de passwords usando `==` en lugar de una funcion de comparacion en tiempo constante.

**Ejemplo de codigo vulnerable:**

```python
if user.password == provided_password:    # Vulnerable a timing attacks
    return True
```

**Correccion:**

```python
import hmac
if hmac.compare_digest(user.password_hash, computed_hash):
    return True
```

---

## CAT-03: Secrets & Credentials

> **Estado: IMPLEMENTADO** — El `SecretsAnalyzer` esta activo desde v0.3.0. Las reglas SEC-001 a SEC-004 y SEC-006 estan implementadas. SEC-005 esta diferida (requiere analisis de .gitignore). Soporta Python y JavaScript/TypeScript.

Detecta secrets y credenciales que los agentes de IA copian de ejemplos o generan de forma insegura.

### SEC-001 — Placeholder secret in code

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |
| CWE | CWE-798 |

**Que detecta:** Un valor que parece un placeholder copiado de `.env.example` o documentacion.

**Ejemplo de codigo vulnerable:**

```python
API_KEY = "your-api-key-here"      # Placeholder copiado
DATABASE_URL = "changeme"           # Placeholder
```

---

### SEC-002 — Low-entropy hardcoded secret

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |
| CWE | CWE-798 |

**Que detecta:** Secret hardcodeado con entropia baja (probablemente generado por el agente de IA sin cuidado).

**Ejemplo:** `SECRET = "abc123"` tiene entropia mucho menor que un secret real.

---

### SEC-003 — Embedded connection string

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |
| CWE | CWE-798 |

**Que detecta:** Connection strings con credenciales embebidas.

**Ejemplo de codigo vulnerable:**

```python
DATABASE_URL = "postgresql://admin:password123@db.example.com:5432/mydb"
MONGO_URI = "mongodb://root:secret@mongo:27017/app"
```

---

### SEC-004 — Sensitive env with default value

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |

**Que detecta:** Variable de entorno sensible con un valor por defecto hardcodeado en el codigo.

**Ejemplo de codigo vulnerable:**

```python
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-not-for-production")
```

---

### SEC-005 — Secret file not in gitignore (pendiente)

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |
| Estado | **Diferida** — requiere analisis de `.gitignore` |

**Que detecta:** Archivos que contienen credenciales o keys y no estan listados en `.gitignore`.

**Archivos tipicos:** `.env`, `credentials.json`, `*.pem`, `*.key`

---

### SEC-006 — Value copied from env example

| Campo | Valor |
|-------|-------|
| Severidad | CRITICAL |

**Que detecta:** Un valor en el codigo que coincide textualmente con un valor del archivo `.env.example`.

**Ejemplo:** Si `.env.example` tiene `API_KEY=sk-example-key-12345` y el codigo tiene `api_key = "sk-example-key-12345"`, vigil lo detecta.

---

## CAT-06: Test Quality

> **Estado: PENDIENTE** — Las reglas TEST-001 a TEST-006 estan definidas pero el `TestQualityAnalyzer` aun no esta implementado (FASE 3).

Detecta tests que dan cobertura falsa — pasan pero no verifican nada real. Esto se conoce como "test theater".

### TEST-001 — Test without assertions

| Campo | Valor |
|-------|-------|
| Severidad | HIGH |

**Que detecta:** Una funcion de test que no contiene ningun assert, verify, expect ni similar.

**Ejemplo de codigo vulnerable:**

```python
def test_login():
    response = client.post("/login", json={"user": "admin", "pass": "123"})
    # No hay assert — el test siempre pasa
```

---

### TEST-002 — Trivial assertion

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |

**Que detecta:** Assert que solo verifica condiciones triviales como `is not None` o `assertTrue(True)`.

**Ejemplo de codigo vulnerable:**

```python
def test_user_exists():
    user = get_user(1)
    assert user is not None    # Trivial: no verifica el contenido
```

---

### TEST-003 — Assert catches all exceptions

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |

**Que detecta:** Tests que usan `except Exception: pass` o `except: pass`, ocultando errores reales.

**Ejemplo de codigo vulnerable:**

```python
def test_complex_operation():
    try:
        result = complex_operation()
    except Exception:    # Captura todo, el test nunca falla
        pass
```

---

### TEST-004 — Skipped test without reason

| Campo | Valor |
|-------|-------|
| Severidad | LOW |

**Que detecta:** Tests marcados con `@pytest.mark.skip` o `@unittest.skip` sin un argumento `reason`.

---

### TEST-005 — No status code assertion in API test

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |

**Que detecta:** Tests que hacen requests HTTP pero no verifican el status code de la respuesta.

---

### TEST-006 — Mock mirrors implementation

| Campo | Valor |
|-------|-------|
| Severidad | MEDIUM |

**Que detecta:** Mocks cuyo valor de retorno es exactamente el valor que el test espera, creando un test circular que no verifica logica real.

**Ejemplo de codigo vulnerable:**

```python
def test_calculate():
    with patch("app.calculate") as mock:
        mock.return_value = 42        # El mock retorna 42
        result = app.calculate(6, 7)
        assert result == 42           # ...y el test espera 42. No se testo nada.
```
