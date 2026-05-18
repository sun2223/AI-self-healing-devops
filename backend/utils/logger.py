"""
PULSE DevOps Agent — Structured Logger

WHY structlog?
  - Outputs JSON logs in production (easy to parse in log aggregators)
  - Human-readable colored output in development
  - Automatically adds timestamps, module names, log levels
  - Works with FastAPI's async context

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened", run_id="abc123", file="main.py")
"""

import logging
import sys
import structlog
from core.config import settings


def setup_logging():
    """
    Configure structlog for the entire application.
    Called once at startup in main.py
    """

    # Set log level from environment
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Processors determine how log entries look
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.dev.set_exc_info,
    ]

    if settings.DEBUG:
        # Human-readable colored output for development
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a logger for a module.

    Args:
        name: Module name — use __name__ for automatic naming

    Returns:
        Configured structlog bound logger

    Example:
        logger = get_logger(__name__)
        logger.info("Scan started", run_id="abc", repo="myrepo/test")
        logger.error("Fix failed", error="SyntaxError", file="main.py")
    """
    return structlog.get_logger(name)
