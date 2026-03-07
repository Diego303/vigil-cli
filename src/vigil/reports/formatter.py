"""Base formatter y factory para output de vigil."""

from typing import Any, Protocol

from vigil.core.engine import ScanResult


class BaseFormatter(Protocol):
    """Protocolo para formatters de output."""

    def format(self, result: ScanResult) -> str:
        """Formatea el resultado del scan a string."""
        ...


def get_formatter(format_name: str, **kwargs: Any) -> BaseFormatter:
    """Factory que retorna el formatter adecuado.

    Args:
        format_name: Nombre del formato ("human", "json", "junit", "sarif").
        **kwargs: Opciones adicionales para el formatter. Para "human":
            colors (bool), show_suggestions (bool), quiet (bool).
    """
    factories: dict[str, Any] = {
        "human": _get_human_formatter,
        "json": _get_json_formatter,
        "junit": _get_junit_formatter,
        "sarif": _get_sarif_formatter,
    }
    factory = factories.get(format_name)
    if not factory:
        raise ValueError(
            f"Unknown format: {format_name}. "
            f"Available: {', '.join(factories)}"
        )
    return factory(**kwargs)


def _get_human_formatter(**kwargs: Any) -> BaseFormatter:
    from vigil.reports.human import HumanFormatter
    return HumanFormatter(**kwargs)


def _get_json_formatter(**kwargs: Any) -> BaseFormatter:
    from vigil.reports.json_fmt import JsonFormatter
    return JsonFormatter()


def _get_junit_formatter(**kwargs: Any) -> BaseFormatter:
    from vigil.reports.junit import JunitFormatter
    return JunitFormatter()


def _get_sarif_formatter(**kwargs: Any) -> BaseFormatter:
    from vigil.reports.sarif import SarifFormatter
    return SarifFormatter()
