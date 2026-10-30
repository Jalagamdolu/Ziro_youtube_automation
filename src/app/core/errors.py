class RetryableError(Exception):
    """Timeout, 429 or 5xx: retried with exponential backoff up to the stage's attempt limit."""


class FatalError(Exception):
    """Validation failure, claim-check failure or missing input: never retried."""
