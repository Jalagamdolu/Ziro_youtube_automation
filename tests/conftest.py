"""Shared fixtures. DB-backed tests run inside the compose network (D-16) against a separate
`ziro_test` database and Redis DB 1, truncated before each test. No paid API is ever called.
"""

import os
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

BASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@postgres:5432/ziro")
TEST_DB_URL = BASE_URL.rsplit("/", 1)[0] + "/ziro_test"
os.environ["DATABASE_URL"] = TEST_DB_URL
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
os.environ["REDIS_URL"] = REDIS_URL.rsplit("/", 1)[0] + "/1"

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("approvals", "artifacts", "costs", "events", "jobs", "publishing", "sources",
          "asset_licenses", "projects", "checkpoints", "checkpoint_writes", "checkpoint_blobs")


@pytest.fixture(scope="session")
def database() -> None:
    with psycopg.connect(BASE_URL, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'ziro_test'").fetchone():
            conn.execute("CREATE DATABASE ziro_test")
    subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, check=True)
    from app.graph.build import setup_checkpoints

    setup_checkpoints()


@pytest.fixture
def pipeline(database: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clean tables, a temp runs/ dir, fast retries and a synchronous queue."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {', '.join(TABLES)} CASCADE")
    from rq import Queue

    from app.core import config
    from app.jobs import queue

    queue.redis().flushdb()
    import app.nodes as nodes
    from app.nodes import stubs

    # The API/test image has no media stack (D-24); real rendering runs in the worker image.
    monkeypatch.setitem(nodes.FUNCS, "rendering", stubs.rendering)
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    cfg = config.load()
    cfg["backoff"] = {"initial_seconds": 0.01, "factor": 2.0, "max_seconds": 0.05}
    monkeypatch.setattr(config, "load", lambda: cfg)
    monkeypatch.setattr(queue, "queue", lambda: Queue(queue.QUEUE_NAME, connection=queue.redis(),
                                                       is_async=False))
    yield


@pytest.fixture
def calls(pipeline: None, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Counts how often each stage implementation actually executes (cache hits excluded)."""
    import app.nodes as nodes

    counter: Counter[str] = Counter()
    for stage, func in list(nodes.FUNCS.items()):
        monkeypatch.setitem(nodes.FUNCS, stage, _counting(stage, func, counter))
    return counter


def _counting(
    stage: str, func: Callable[[Any], Any], counter: Counter[str]
) -> Callable[[Any], Any]:
    def wrapped(ctx: Any) -> Any:
        counter[stage] += 1
        return func(ctx)

    return wrapped


@pytest.fixture
def client(pipeline: None) -> Any:
    from fastapi.testclient import TestClient

    from app.api.main import app

    return TestClient(app)  # not entered as a context manager, so the reaper thread stays off


DISCLOSURE = {"synthetic": True, "reason": "AI narration and generated visuals"}
SHORT_TOPIC = "What makes an AI agent different from a chatbot?"  # has a prototype fixture


def create(client: Any, **overrides: Any) -> str:
    body = {"prompt": SHORT_TOPIC, "format": "short"}
    response = client.post("/projects", json=body | overrides)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def approve(client: Any, project_id: str, **extra: Any) -> Any:
    return client.post(f"/projects/{project_id}/approve", json={"reviewer": "Dolender"} | extra)


def reject(client: Any, project_id: str, target: str, notes: str = "needs work") -> Any:
    return client.post(f"/projects/{project_id}/reject",
                       json={"reviewer": "Dolender", "target": target, "notes": notes})


def status(client: Any, project_id: str) -> dict[str, Any]:
    return dict(client.get(f"/projects/{project_id}").json())


def run_to_qa_review(client: Any, **overrides: Any) -> str:
    project_id = create(client, **overrides)
    assert approve(client, project_id).status_code == 202  # research_review
    assert approve(client, project_id).status_code == 202  # script_review
    assert status(client, project_id)["status"] == "qa_review"
    return project_id
