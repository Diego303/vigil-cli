"""Finding, Severity, Category — modelos de datos centrales de vigil."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Severidad del hallazgo."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Category(str, Enum):
    """Categoria del check."""

    DEPENDENCY = "dependency"
    AUTH = "auth"
    SECRETS = "secrets"
    TEST_QUALITY = "test-quality"


@dataclass
class Location:
    """Ubicacion del hallazgo en el codigo."""

    file: str
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    snippet: str | None = None


@dataclass
class Finding:
    """Un hallazgo individual de vigil."""

    rule_id: str
    category: Category
    severity: Severity
    message: str
    location: Location
    suggestion: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocking(self) -> bool:
        """Este finding deberia bloquear el merge."""
        return self.severity in (Severity.CRITICAL, Severity.HIGH)
