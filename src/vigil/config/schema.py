"""Pydantic models de configuracion de vigil."""

from typing import Literal

from pydantic import BaseModel, Field


class RuleOverride(BaseModel):
    """Override de una regla especifica."""

    enabled: bool | None = None
    severity: str | None = None


class DepsConfig(BaseModel):
    """Configuracion del analyzer de dependencias."""

    verify_registry: bool = True
    min_age_days: int = 30
    min_weekly_downloads: int = 100
    similarity_threshold: float = 0.85
    cache_ttl_hours: int = 24
    offline_mode: bool = False
    popular_packages_file: str | None = None


class AuthConfig(BaseModel):
    """Configuracion del analyzer de auth."""

    max_token_lifetime_hours: int = 24
    require_auth_on_mutating: bool = True
    cors_allow_localhost: bool = True


class SecretsConfig(BaseModel):
    """Configuracion del analyzer de secrets."""

    min_entropy: float = 3.0
    check_env_example: bool = True
    placeholder_patterns: list[str] = Field(
        default_factory=lambda: [
            "changeme",
            r"your[-_].*[-_]here",
            r"replace[-_]?me",
            r"insert[-_].*[-_]here",
            r"put[-_].*[-_]here",
            r"add[-_].*[-_]here",
            "TODO",
            "FIXME",
            "xxx+",
            r"sk[-_]your.*",
            r"pk[-_]test[-_].*",
            r"sk[-_]test[-_].*",
            r"sk[-_]live[-_]test.*",
            "secret123",
            "password123",
            "supersecret",
            "mysecret",
            r"my[-_]?secret[-_]?key",
            r"example\.com",
            r"test[-_]?key",
            r"test[-_]?secret",
            r"dummy[-_]?key",
            r"dummy[-_]?secret",
            r"fake[-_]?key",
            r"fake[-_]?secret",
            r"sample[-_]?key",
            r"sample[-_]?secret",
            r"default[-_]?secret",
            r"default[-_]?key",
            "placeholder",
        ]
    )


class TestQualityConfig(BaseModel):
    """Configuracion del analyzer de test quality."""

    __test__ = False  # Prevent pytest collection

    min_assertions_per_test: int = 1
    detect_trivial_asserts: bool = True
    detect_mock_mirrors: bool = True


class OutputConfig(BaseModel):
    """Configuracion de output."""

    format: str = "human"
    output_file: str | None = None
    colors: bool = True
    verbose: bool = False
    show_suggestions: bool = True


class ScanConfig(BaseModel):
    """Configuracion principal de vigil."""

    # Paths
    include: list[str] = Field(default_factory=lambda: ["src/", "lib/", "app/"])
    exclude: list[str] = Field(
        default_factory=lambda: [
            "node_modules/",
            ".venv/",
            "__pycache__/",
            ".git/",
            "dist/",
            "build/",
            ".tox/",
            ".mypy_cache/",
        ]
    )
    test_dirs: list[str] = Field(default_factory=lambda: ["tests/", "test/", "__tests__/"])

    # Severidades
    fail_on: Literal["critical", "high", "medium", "low", "info"] = "high"

    # Analyzers
    deps: DepsConfig = Field(default_factory=DepsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    tests: TestQualityConfig = Field(default_factory=TestQualityConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    # Rule overrides
    rules: dict[str, RuleOverride] = Field(default_factory=dict)

    # Languages
    languages: list[str] = Field(default_factory=lambda: ["python", "javascript"])

    # Filtros de runtime (set por CLI, no por YAML)
    categories: list[str] = Field(default_factory=list)
    rules_filter: list[str] = Field(default_factory=list)
    exclude_rules: list[str] = Field(default_factory=list)
