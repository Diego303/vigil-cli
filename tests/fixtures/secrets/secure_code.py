"""Fixture: Secure code — should NOT generate secret findings."""

import os

# Proper environment variable usage
API_KEY = os.environ["API_KEY"]
SECRET_KEY = os.getenv("SECRET_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Non-sensitive assignments
APP_NAME = "my-app"
VERSION = "1.0.0"
DEBUG = True
MAX_RETRIES = 3
LOG_LEVEL = "info"

# Connection string from env var
db_url = os.environ["DATABASE_URL"]
