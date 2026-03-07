"""Fixture: FastAPI app with multiple auth issues."""

from datetime import datetime, timedelta
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import jwt

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])  # AUTH-005

SECRET = "supersecret123"  # AUTH-004

@app.delete("/users/{user_id}")  # AUTH-002 (no auth)
async def delete_user(user_id: int):
    return {"deleted": user_id}

@app.post("/login")
async def login():
    token = jwt.encode(
        {"exp": datetime.utcnow() + timedelta(hours=72)},  # AUTH-003
        SECRET
    )
    return {"token": token}

@app.get("/admin/dashboard")  # AUTH-001 (sensitive path, no auth)
async def admin_dashboard():
    return {"data": "secret admin data"}

# Legitimate endpoint with auth — should NOT trigger
@app.get("/users/me")
async def get_me(user = Depends(get_current_user)):
    return user
