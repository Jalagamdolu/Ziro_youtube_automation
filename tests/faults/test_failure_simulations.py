"""Brief §08 failure simulations. Unsourced claim lives in graph/test_claim_ledger_review.py;
missing OAuth token waits for the publisher work in Phase 6P.
"""

import os
from collections import Counter
from pathlib import Path

from conftest import DISCLOSURE, approve, create, reject, run_to_qa_review, status
from rq import Queue, SimpleWorker
from sqlalchemy import func, select

import app.nodes as nodes
from app.core import db
from app.core.errors import RetryableError
from app.core.models import Publishing
from app.jobs import queue


def _publish_rows(project_id: str) -> int:
    with db.session() as s:
        return s.scalar(select(func.count()).where(Publishing.project_id == project_id)) or 0


def test_rejected_script_never_renders(client, calls: Counter[str]) -> None:
    project_id = create(client)
    approve(client, project_id)
    assert reject(client, project_id, "scripting", notes="unsupported claim").status_code == 202

    run = status(client, project_id)
    assert run["status"] == "script_review"  # back at the editable script stage
    assert calls["storyboarding"] == calls["rendering"] == calls["mock_published"] == 0
    assert run["approvals"][-1]["decision"] == "reject"  # decision retained


def test_duplicate_publish_click_yields_one_job(client, monkeypatch) -> None:
    project_id = run_to_qa_review(client)
    async_queue = Queue(queue.QUEUE_NAME, connection=queue.redis())
    monkeypatch.setattr(queue, "queue", lambda: async_queue)  # enqueue only; run below

    first = approve(client, project_id, ai_disclosure=DISCLOSURE)
    second = approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert (first.status_code, second.status_code) == (202, 409)
    assert async_queue.count == 1

    SimpleWorker([async_queue], connection=queue.redis()).work(burst=True)
    assert status(client, project_id)["status"] == "done"
    assert _publish_rows(project_id) == 1


def test_rate_limit_backs_off_without_duplicate(client, monkeypatch) -> None:
    real = nodes.FUNCS["mock_published"]
    limited = iter(range(2))

    def rate_limited(ctx):
        if next(limited, None) is not None:
            raise RetryableError("429 quotaExceeded")
        return real(ctx)

    monkeypatch.setitem(nodes.FUNCS, "mock_published", rate_limited)
    project_id = run_to_qa_review(client)
    approve(client, project_id, ai_disclosure=DISCLOSURE)

    run = status(client, project_id)
    assert run["status"] == "done"
    assert [j["status"] for j in run["jobs"] if j["stage"] == "mock_published"] == [
        "failed", "failed", "succeeded"]
    assert _publish_rows(project_id) == 1


def test_renderer_timeout_fails_keeps_artifacts_then_manual_retry(client, monkeypatch) -> None:
    real = nodes.FUNCS["rendering"]

    def timeout(ctx):
        raise RetryableError("render timed out after 1800s")

    monkeypatch.setitem(nodes.FUNCS, "rendering", timeout)
    project_id = create(client)
    approve(client, project_id)
    approve(client, project_id)

    run = status(client, project_id)
    assert run["status"] == "failed"
    rendering_jobs = [j for j in run["jobs"] if j["stage"] == "rendering"]
    assert len(rendering_jobs) == 2  # config: render gets 2 attempts
    runs_dir = Path(os.environ["RUNS_DIR"])
    assert all((runs_dir / a["storage_path"]).exists() for a in run["artifacts"])
    assert {a["stage"] for a in run["artifacts"]} >= {"scripting", "storyboarding"}

    monkeypatch.setitem(nodes.FUNCS, "rendering", real)
    assert client.post(f"/projects/{project_id}/retry").status_code == 202
    assert status(client, project_id)["status"] == "qa_review"
