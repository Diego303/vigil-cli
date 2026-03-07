"""Fixture: Python file with multiple secret issues."""

import os

# SEC-001: Placeholder secrets
API_KEY = "your-api-key-here"
SECRET_KEY = "changeme"
JWT_SECRET = "supersecret"

# SEC-002: Low-entropy hardcoded secrets
DB_PASSWORD = "password123"
AUTH_TOKEN = "abc123def"

# SEC-003: Connection strings with embedded credentials
DATABASE_URL = "postgresql://admin:secretpass@db.example.com:5432/myapp"
REDIS_URL = "redis://user:redispass@redis.example.com:6379/0"

# SEC-004: Env var with default value
STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "sk_test_abc123xyz")
DB_PASS = os.getenv("DB_PASSWORD", "devpassword123")

# This should NOT trigger — proper env var usage
SAFE_KEY = os.environ["API_KEY"]
SAFE_SECRET = os.getenv("SECRET_KEY")
