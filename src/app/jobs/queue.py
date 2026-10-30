from functools import cache
from typing import Any

from redis import Redis
from rq import Queue

from app.core import config
from app.jobs.advance import advance

QUEUE_NAME = "ziro"
DEDUPE_SECONDS = 7 * 24 * 3600


@cache
def redis() -> Redis:
    return Redis.from_url(config.redis_url())


def queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis())


def enqueue_once(job_id: str, project_id: str, resume: dict[str, Any] | None = None) -> bool:
    """Enqueue advance() under job_id ("project_id:stage:attempt") unless that id was already used.

    Redis SET NX makes duplicate clicks collapse to one job, even when they race (D-06).
    """
    if not redis().set(f"ziro:job:{job_id}", "1", nx=True, ex=DEDUPE_SECONDS):
        return False
    timeout = max(config.load()["stage_deadline_seconds"].values())
    rq_id = job_id.replace(":", "-")  # RQ 3 allows only letters, digits, _ and -
    queue().enqueue(advance, project_id, resume, job_id=rq_id, job_timeout=timeout)
    return True
