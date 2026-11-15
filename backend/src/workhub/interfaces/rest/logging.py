"""Logging structuré JSON (structlog) pour les interfaces HTTP."""

from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging(level: str | None = None) -> None:
    """Configure structlog en JSON et le pont avec `logging` (idempotent).

    Le niveau vient de l'argument, sinon de `LOG_LEVEL`, sinon `INFO`. Une valeur inconnue
    retombe sur `INFO` après un avertissement, pour ne pas empêcher le démarrage.
    """
    resolved = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    log_level = logging.getLevelNamesMapping().get(resolved)
    invalid_level = log_level is None
    if log_level is None:
        log_level = logging.INFO

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )
    if invalid_level:
        logging.getLogger(__name__).warning(
            "log_level.invalid",
            extra={"requested_level": resolved, "fallback_level": "INFO"},
        )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Retourne un logger structuré nommé."""
    return structlog.get_logger(name)
