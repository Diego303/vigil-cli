"""Fixture: Edge cases for auth detection."""

from datetime import timedelta

# Edge case: JWT timedelta with days (not hours)
exp = timedelta(days=30)  # AUTH-003: 720 hours

# Edge case: JWT at exactly 24h threshold — should NOT trigger with default config
exp_ok = timedelta(hours=24)

# Edge case: Multiple CORS origins, one is *
# This should trigger because '*' is present
# allow_origins=["https://myapp.com", "*"]

# Edge case: Password in a timing-safe comparison — should NOT trigger
result = hmac.compare_digest(password, stored)

# Edge case: Cookie with partial flags
response.set_cookie(
    "session", "value",
    secure=True,
    # Missing: httponly, samesite
)

# Edge case: Secret that looks like a config reference — should NOT trigger
SECRET_KEY = "settings.SECRET_KEY_VALUE"
