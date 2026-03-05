"""Fixtures compartidas para tests de vigil."""

from pathlib import Path

import pytest

from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding, Location, Severity


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def default_config() -> ScanConfig:
    return ScanConfig()


@pytest.fixture
def sample_finding() -> Finding:
    return Finding(
        rule_id="DEP-001",
        category=Category.DEPENDENCY,
        severity=Severity.CRITICAL,
        message="Package 'fake-pkg' does not exist in pypi.",
        location=Location(file="requirements.txt", line=3),
        suggestion="Remove 'fake-pkg' and find the correct package name.",
        metadata={"package": "fake-pkg", "ecosystem": "pypi"},
    )


@pytest.fixture
def sample_findings() -> list[Finding]:
    """Conjunto de findings de diferentes severidades para testing."""
    return [
        Finding(
            rule_id="DEP-001",
            category=Category.DEPENDENCY,
            severity=Severity.CRITICAL,
            message="Package 'nonexistent-lib' does not exist in pypi.",
            location=Location(file="requirements.txt", line=5),
            suggestion="Remove this dependency.",
        ),
        Finding(
            rule_id="AUTH-005",
            category=Category.AUTH,
            severity=Severity.HIGH,
            message="CORS configured with '*' allowing requests from any origin.",
            location=Location(file="src/main.py", line=8),
            suggestion="Restrict CORS to specific trusted origins.",
        ),
        Finding(
            rule_id="AUTH-003",
            category=Category.AUTH,
            severity=Severity.MEDIUM,
            message="JWT with lifetime of 72 hours.",
            location=Location(file="src/auth.py", line=31, snippet='expiresIn: "72h"'),
        ),
        Finding(
            rule_id="TEST-004",
            category=Category.TEST_QUALITY,
            severity=Severity.LOW,
            message="Test marked as skip without justification.",
            location=Location(file="tests/test_app.py", line=10),
        ),
    ]
