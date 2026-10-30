"""A worker killed mid-node is resumed by the reaper without re-running completed nodes.

The kill is simulated in-process: the node raises a BaseException, which (like SIGKILL) escapes
every `except Exception`, so the job row stays "running" and no checkpoint is written for that node.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

from conftest import approve, create, status

import app.nodes as nodes
from app.jobs.reaper import reap


class WorkerKilled(BaseException):
    pass


def test_reaper_resumes_after_kill(client, calls: Counter[str], monkeypatch) -> None:
    project_id = create(client)
    approve(client, project_id)

    real = nodes.FUNCS["storyboarding"]
    kills = iter([True])

    def dies_once(ctx):
        if next(kills, False):
            raise WorkerKilled
        return real(ctx)

    monkeypatch.setitem(nodes.FUNCS, "storyboarding", dies_once)
    approve(client, project_id)  # script_review → storyboarding, killed mid-node
    run = status(client, project_id)
    assert run["status"] == "storyboarding"
    assert [j["status"] for j in run["jobs"] if j["stage"] == "storyboarding"] == ["running"]

    assert reap() == []  # within the deadline: left alone
    assert reap(datetime.now(UTC) + timedelta(hours=1)) == [project_id]

    run = status(client, project_id)
    assert run["status"] == "qa_review"
    assert calls["draft"] == calls["researching"] == calls["scripting"] == 1
    story_jobs = [j["status"] for j in run["jobs"] if j["stage"] == "storyboarding"]
    assert story_jobs == ["abandoned", "succeeded"]
