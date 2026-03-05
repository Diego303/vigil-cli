"""Configuracion de structlog para vigil."""

import logging
import sys

import structlog


def setup_logging(verbose: bool = False) -> None:
    """Configura structlog para output a stderr.

    En modo no-verbose, solo muestra warnings y errores.
    En modo verbose, muestra todo incluido debug.
    Los logs van a stderr para no mezclarse con output de findings (stdout).
    """
    log_level = logging.DEBUG if verbose else logging.WARNING

    # Configurar logging estandar (para que structlog lo use como backend)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer() if verbose else _minimal_renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _minimal_renderer(
    logger: object,
    method_name: str,
    event_dict: dict,
) -> str:
    """Renderer minimalista para modo no-verbose."""
    event = event_dict.get("event", "")
    level = event_dict.get("level", "info")
    return f"[{level}] {event}"
