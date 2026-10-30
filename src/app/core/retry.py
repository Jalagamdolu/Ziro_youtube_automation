from typing import Any

from langgraph.types import RetryPolicy

from app.core.errors import RetryableError


def policy(stage: str, cfg: dict[str, Any]) -> RetryPolicy | None:
    """Per-stage LangGraph retry policy; only RetryableError is retried. None = single attempt."""
    attempts = cfg["retries"].get(stage)
    if not attempts:
        return None
    backoff = cfg["backoff"]
    return RetryPolicy(
        max_attempts=attempts,
        initial_interval=backoff["initial_seconds"],
        backoff_factor=backoff["factor"],
        max_interval=backoff["max_seconds"],
        jitter=True,
        retry_on=RetryableError,
    )
