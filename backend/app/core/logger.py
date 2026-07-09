"""Structured logging configuration using structlog.

Provides context-aware logging with request IDs, correlation IDs,
and different formatting for development (coloured console) vs
production (JSON for log aggregators).
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.processors import StackInfoRenderer, TimeStamper, format_exc_info
from structlog.typing import EventDict, WrappedLogger

from app.core.config import settings, Environment

# Module-level context variable for request ID — set by middleware
request_id_var: ContextVar[str] = ContextVar('request_id', default='')


def add_app_context(logger: WrappedLogger, name: str, event_dict: EventDict) -> EventDict:
    """Attach static application metadata to every log event."""
    event_dict['app'] = settings.app_name
    event_dict['version'] = settings.app_version
    event_dict['environment'] = settings.environment.value
    return event_dict


def add_request_id_processor(logger: WrappedLogger, name: str, event_dict: EventDict) -> EventDict:
    """Attach request_id from the current context if available."""
    rid = request_id_var.get()
    if rid:
        event_dict['request_id'] = rid
    return event_dict


def drop_color_message(_, __, event_dict: EventDict) -> EventDict:
    """Drop the 'color_message' key added by structlog's ColorDiFormatter."""
    event_dict.pop('color_message', None)
    return event_dict


def setup_logging() -> None:
    """Configure structlog as the global logging framework.

    Call once during application startup (``main.py``).
    """
    timestamper = TimeStamper(fmt='iso', utc=True)

    shared_processors: list[Any] = [
        add_app_context,
        add_request_id_processor,
        timestamper,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        StackInfoRenderer(),
        format_exc_info,
    ]

    if settings.is_development:
        # Development: colourful terminal output
        processors: list[Any] = [
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                drop_color_message,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            foreign_pre_chain=shared_processors,
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # Production: JSON output for log aggregators
        processors: list[Any] = [
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ]
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        # Silence noisy third-party loggers
        logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)

    # Quiet the default uvicorn logger in dev too
    logging.getLogger('uvicorn.error').setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structured logger instance.

    Usage::

        from app.core.logger import get_logger
        log = get_logger(__name__)
        log.info('event_name', key='value', user_id='abc')
    """
    return structlog.get_logger(name or __name__)


# Module-level shortcut
log = get_logger('mentis')
