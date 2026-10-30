"""structlog JSON logging. Every line carries project_id, stage and attempt (CLAUDE.md)."""

import re

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.typing import EventDict, WrappedLogger

SECRET_KEY = re.compile(r"key|token|secret|password|authorization|credential", re.IGNORECASE)


def _require_context(_: WrappedLogger, __: str, event: EventDict) -> EventDict:
    for name in ("project_id", "stage", "attempt"):
        event.setdefault(name, None)
    return event


def _redact(_: WrappedLogger, __: str, event: EventDict) -> EventDict:
    for name in event:
        if SECRET_KEY.search(name):
            event[name] = "[redacted]"
    return event


structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _require_context,
        _redact,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()

__all__ = ["bind_contextvars", "clear_contextvars", "log"]
