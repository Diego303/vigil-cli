"""Catalogo de reglas built-in de vigil V0."""

from dataclasses import dataclass, field

from vigil.core.finding import Category, Severity


@dataclass
class RuleDefinition:
    """Definicion de una regla de vigil."""

    id: str
    name: str
    description: str
    category: Category
    default_severity: Severity
    enabled_by_default: bool = True
    languages: list[str] = field(default_factory=list)
    owasp_ref: str | None = None
    cwe_ref: str | None = None


RULES_V0: list[RuleDefinition] = [
    # ──────────────────────────────────────────────
    # CAT-01: Dependency Hallucination
    # ──────────────────────────────────────────────
    RuleDefinition(
        id="DEP-001",
        name="Hallucinated dependency",
        description="Package declared as dependency does not exist in the public registry.",
        category=Category.DEPENDENCY,
        default_severity=Severity.CRITICAL,
        owasp_ref="LLM03",
        cwe_ref="CWE-829",
    ),
    RuleDefinition(
        id="DEP-002",
        name="Suspiciously new dependency",
        description="Package exists but was published less than 30 days ago.",
        category=Category.DEPENDENCY,
        default_severity=Severity.HIGH,
        owasp_ref="LLM03",
    ),
    RuleDefinition(
        id="DEP-003",
        name="Typosquatting candidate",
        description="Package name is very similar to a popular package.",
        category=Category.DEPENDENCY,
        default_severity=Severity.HIGH,
        owasp_ref="LLM03",
        cwe_ref="CWE-829",
    ),
    RuleDefinition(
        id="DEP-004",
        name="Unpopular dependency",
        description="Package has very few weekly downloads (<100).",
        category=Category.DEPENDENCY,
        default_severity=Severity.MEDIUM,
    ),
    RuleDefinition(
        id="DEP-005",
        name="No source repository",
        description="Package has no linked source code repository.",
        category=Category.DEPENDENCY,
        default_severity=Severity.MEDIUM,
    ),
    RuleDefinition(
        id="DEP-006",
        name="Missing dependency",
        description="Import in code references a module not declared in dependencies.",
        category=Category.DEPENDENCY,
        default_severity=Severity.HIGH,
    ),
    RuleDefinition(
        id="DEP-007",
        name="Nonexistent version",
        description="The specified version of the package does not exist in the registry.",
        category=Category.DEPENDENCY,
        default_severity=Severity.CRITICAL,
    ),
    # ──────────────────────────────────────────────
    # CAT-02: Auth & Permission Patterns
    # ──────────────────────────────────────────────
    RuleDefinition(
        id="AUTH-001",
        name="Unprotected sensitive endpoint",
        description="Endpoint handling sensitive data without authentication middleware.",
        category=Category.AUTH,
        default_severity=Severity.HIGH,
        owasp_ref="LLM06",
        cwe_ref="CWE-306",
    ),
    RuleDefinition(
        id="AUTH-002",
        name="Destructive endpoint without authorization",
        description="DELETE/PUT endpoint without authorization verification.",
        category=Category.AUTH,
        default_severity=Severity.HIGH,
        cwe_ref="CWE-862",
    ),
    RuleDefinition(
        id="AUTH-003",
        name="Excessive token lifetime",
        description="JWT with lifetime exceeding 24 hours.",
        category=Category.AUTH,
        default_severity=Severity.MEDIUM,
    ),
    RuleDefinition(
        id="AUTH-004",
        name="Hardcoded JWT secret",
        description="JWT secret hardcoded with placeholder value or low entropy.",
        category=Category.AUTH,
        default_severity=Severity.CRITICAL,
        cwe_ref="CWE-798",
    ),
    RuleDefinition(
        id="AUTH-005",
        name="CORS allow all origins",
        description="CORS configured with '*' allowing requests from any origin.",
        category=Category.AUTH,
        default_severity=Severity.HIGH,
        cwe_ref="CWE-942",
    ),
    RuleDefinition(
        id="AUTH-006",
        name="Insecure cookie configuration",
        description="Cookie without httpOnly, secure, or sameSite flags.",
        category=Category.AUTH,
        default_severity=Severity.MEDIUM,
        cwe_ref="CWE-614",
    ),
    RuleDefinition(
        id="AUTH-007",
        name="Password comparison not timing-safe",
        description="Password comparison without constant-time comparison.",
        category=Category.AUTH,
        default_severity=Severity.MEDIUM,
        cwe_ref="CWE-208",
    ),
    # ──────────────────────────────────────────────
    # CAT-03: Secrets & Credentials
    # ──────────────────────────────────────────────
    RuleDefinition(
        id="SEC-001",
        name="Placeholder secret in code",
        description="Value appears to be a placeholder from .env.example or documentation.",
        category=Category.SECRETS,
        default_severity=Severity.CRITICAL,
        cwe_ref="CWE-798",
    ),
    RuleDefinition(
        id="SEC-002",
        name="Low-entropy hardcoded secret",
        description="Hardcoded secret with low entropy (likely generated by AI agent).",
        category=Category.SECRETS,
        default_severity=Severity.CRITICAL,
        cwe_ref="CWE-798",
    ),
    RuleDefinition(
        id="SEC-003",
        name="Embedded connection string",
        description="Connection string with embedded credentials.",
        category=Category.SECRETS,
        default_severity=Severity.CRITICAL,
        cwe_ref="CWE-798",
    ),
    RuleDefinition(
        id="SEC-004",
        name="Sensitive env with default value",
        description="Sensitive environment variable with hardcoded default value in code.",
        category=Category.SECRETS,
        default_severity=Severity.HIGH,
    ),
    RuleDefinition(
        id="SEC-005",
        name="Secret file not in gitignore",
        description="File containing credentials or keys not listed in .gitignore.",
        category=Category.SECRETS,
        default_severity=Severity.HIGH,
    ),
    RuleDefinition(
        id="SEC-006",
        name="Value copied from env example",
        description="Value in code matches a value from .env.example verbatim.",
        category=Category.SECRETS,
        default_severity=Severity.CRITICAL,
    ),
    # ──────────────────────────────────────────────
    # CAT-06: Test Quality
    # ──────────────────────────────────────────────
    RuleDefinition(
        id="TEST-001",
        name="Test without assertions",
        description="Test function without any assert, verify, or expect call.",
        category=Category.TEST_QUALITY,
        default_severity=Severity.HIGH,
    ),
    RuleDefinition(
        id="TEST-002",
        name="Trivial assertion",
        description="Assert that only verifies 'is not None', 'assertTrue(True)', or similar.",
        category=Category.TEST_QUALITY,
        default_severity=Severity.MEDIUM,
    ),
    RuleDefinition(
        id="TEST-003",
        name="Assert catches all exceptions",
        description="Test catches all exceptions without verifying the type.",
        category=Category.TEST_QUALITY,
        default_severity=Severity.MEDIUM,
    ),
    RuleDefinition(
        id="TEST-004",
        name="Skipped test without reason",
        description="Test marked as skip without justification.",
        category=Category.TEST_QUALITY,
        default_severity=Severity.LOW,
    ),
    RuleDefinition(
        id="TEST-005",
        name="No status code assertion in API test",
        description="API test that does not verify the response status code.",
        category=Category.TEST_QUALITY,
        default_severity=Severity.MEDIUM,
    ),
    RuleDefinition(
        id="TEST-006",
        name="Mock mirrors implementation",
        description="Mock returns exactly what the implementation would calculate.",
        category=Category.TEST_QUALITY,
        default_severity=Severity.MEDIUM,
    ),
]
