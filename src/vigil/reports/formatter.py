"""Base formatter y factory para output de vigil."""

from typing import Protocol

from vigil.core.engine import ScanResult


class BaseFormatter(Protocol):
    """Protocolo para formatters de output."""

    def format(self, result: ScanResult) -> str:
        """Formatea el resultado del scan a string."""
        ...


def get_formatter(format_name: str) -> BaseFormatter:
    """Factory que retorna el formatter adecuado."""
    formatters: dict[str, type] = {
        "human": _get_human_formatter,
        "json": _get_json_formatter,
        "junit": _get_junit_formatter,
        "sarif": _get_sarif_formatter,
    }
    factory = formatters.get(format_name)
    if not factory:
        raise ValueError(f"Unknown format: {format_name}. Available: {', '.join(formatters)}")
    return factory()


def _get_human_formatter() -> BaseFormatter:
    from vigil.reports.human import HumanFormatter
    return HumanFormatter()


def _get_json_formatter() -> BaseFormatter:
    from vigil.reports.json_fmt import JsonFormatter
    return JsonFormatter()


def _get_junit_formatter() -> BaseFormatter:
    from vigil.reports.junit import JunitFormatter
    return JunitFormatter()


def _get_sarif_formatter() -> BaseFormatter:
    from vigil.reports.sarif import SarifFormatter
    return SarifFormatter()
