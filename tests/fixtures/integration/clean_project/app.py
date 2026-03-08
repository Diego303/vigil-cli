"""Clean FastAPI application — should produce zero findings."""
import os
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import jwt

app = FastAPI()

# CORS restricted to specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myapp.example.com"],
)

# Secret from environment variable
SECRET_KEY = os.environ["JWT_SECRET_KEY"]


def get_current_user(token: str = Depends()):
    """Dependency injection for auth."""
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])


@app.delete("/users/{user_id}", dependencies=[Depends(get_current_user)])
async def delete_user(user_id: int, current_user=Depends(get_current_user)):
    """Protected endpoint."""
    return {"deleted": user_id}


@app.post("/login")
async def login(username: str, password: str):
    """JWT with reasonable lifetime."""
    token = jwt.encode(
        {"sub": username, "exp": datetime.utcnow() + timedelta(hours=1)},
        SECRET_KEY,
        algorithm="HS256",
    )
    return {"access_token": token}
