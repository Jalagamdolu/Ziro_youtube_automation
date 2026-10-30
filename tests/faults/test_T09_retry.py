"""T09: a forced failure retries and succeeds, or terminates clearly; artifacts stay intact."""

from collections import Counter

from conftest import approve, create, run_to_qa_review, status

import app.nodes as nodes
from app.core.errors import FatalError, RetryableError


def _fails(times: int, error: Exception, then=None):
    remaining = iter(range(times))

    def stage(ctx):
        if next(remaining, None) is not None:
            raise error
        return then(ctx)

    return stage


def test_retryable_failure_retries_then_succeeds(client, monkeypatch) -> None:
    monkeypatch.setitem(nodes.FUNCS, "rendering",
                        _fails(1, RetryableError("503 from renderer"), nodes.FUNCS["rendering"]))
    project_id = run_to_qa_review(client)

    jobs = [(j["status"], j["error_code"]) for j in status(client, project_id)["jobs"]
            if j["stage"] == "rendering"]
    assert jobs == [("failed", "RetryableError"), ("succeeded", None)]


def test_fatal_failure_ends_failed_with_reason(client, calls: Counter[str], monkeypatch) -> None:
    monkeypatch.setitem(nodes.FUNCS, "scripting", _fails(9, FatalError("claim check failed: C9")))
    project_id = create(client)
    approve(client, project_id)

    run = status(client, project_id)
    assert run["status"] == "failed"
    failed = [j for j in run["jobs"] if j["stage"] == "scripting"]
    assert len(failed) == 1  # fatal errors are never retried
    assert failed[0]["error_code"] == "FatalError"
    assert failed[0]["error_message"] == "claim check failed: C9"
    assert calls["storyboarding"] == 0
