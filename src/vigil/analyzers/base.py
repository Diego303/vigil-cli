"""BaseAnalyzer — protocolo que todos los analyzers deben implementar."""

from typing import Protocol

from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Finding


class BaseAnalyzer(Protocol):
    """Protocolo que todos los analyzers deben implementar."""

    @property
    def name(self) -> str:
        """Nombre del analyzer."""
        ...

    @property
    def category(self) -> Category:
        """Categoria de findings que genera."""
        ...

    def analyze(self, files: list[str], config: ScanConfig) -> list[Finding]:
        """Ejecuta el analisis y retorna findings."""
        ...
