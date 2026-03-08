"""Configuration file with secrets issues."""
import os

# SEC-006: Value copied from .env.example
STRIPE_API_KEY = "sk-test-placeholder-key"

# SEC-001: Placeholder secret
AWS_SECRET_KEY = "your-aws-secret-here"

# SEC-002: Low entropy hardcoded secret
ENCRYPTION_KEY = "aaaaaa"
