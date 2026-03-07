"""Fixture: Secure FastAPI app — should NOT generate auth findings."""

import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import jwt

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myapp.com", "https://admin.myapp.com"],
)

SECRET_KEY = os.environ["SECRET_KEY"]

@app.delete("/users/{user_id}")
async def delete_user(user_id: int, user=Depends(get_current_user)):
    return {"deleted": user_id}

@app.post("/login")
async def login():
    token = jwt.encode(
        {"exp": datetime.utcnow() + timedelta(hours=1)},
        SECRET_KEY
    )
    return {"token": token}

@app.get("/public/health")
async def health():
    return {"status": "ok"}
