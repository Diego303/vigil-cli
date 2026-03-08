"""AI-generated FastAPI application with multiple security issues."""
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import jwt

app = FastAPI()

# AUTH-005: CORS allow all origins
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# AUTH-004 + SEC-001: Hardcoded JWT secret with placeholder value
SECRET_KEY = "supersecret123"


@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """AUTH-002: Destructive endpoint without authorization."""
    return {"deleted": user_id}


@app.post("/login")
async def login(username: str, password: str):
    """AUTH-003: JWT with excessive lifetime."""
    token = jwt.encode(
        {"sub": username, "exp": datetime.utcnow() + timedelta(hours=72)},
        SECRET_KEY,
        algorithm="HS256",
    )
    return {"access_token": token}


@app.get("/admin/users")
async def list_all_users():
    """AUTH-001: Sensitive endpoint without auth."""
    return [{"id": 1, "email": "admin@example.com"}]


# SEC-003: Connection string with embedded credentials
DATABASE_URL = "postgresql://admin:password123@db.example.com:5432/myapp"

# SEC-004: Env var with hardcoded default
import os
API_SECRET = os.environ.get("API_SECRET_KEY", "changeme-default-key")

# AUTH-007: Password comparison not timing-safe
def verify_password(stored: str, provided: str) -> bool:
    if stored_password == provided_password:
        return True
    return False
