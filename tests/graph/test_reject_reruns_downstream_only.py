"""Reject jumps to the named stage with its notes, marks downstream stale, reruns downstream."""

import json
import os
from collections import Counter
from pathlib import Path

from conftest import approve, create, reject, run_to_qa_review, status


def test_qa_reject_reruns_from_rendering_only(client, calls: Counter[str]) -> None:
    project_id = run_to_qa_review(client)
    assert reject(client, project_id, "rendering", notes="captions overlap CTA").status_code == 202

    assert status(client, project_id)["status"] == "qa_review"
    assert calls["draft"] == calls["researching"] == calls["scripting"] == 1
    assert calls["storyboarding"] == 1  # upstream of the target: never re-paid
    assert calls["rendering"] == 2

    artifacts = status(client, project_id)["artifacts"]
    rendering = {a["version"]: a for a in artifacts if a["type"] == "qa_report.json"}
    assert rendering[1]["stale"] is True and rendering[2]["stale"] is False
    report = Path(os.environ["RUNS_DIR"]) / rendering[2]["storage_path"]
    assert json.loads(report.read_text())["notes"] == "captions overlap CTA"


def test_script_reject_reruns_scripting_not_research(client, calls: Counter[str]) -> None:
    project_id = create(client)
    approve(client, project_id)
    assert reject(client, project_id, "scripting", notes="hook 1 overclaims").status_code == 202

    run = status(client, project_id)
    assert run["status"] == "script_review"
    assert calls["researching"] == 1 and calls["scripting"] == 2
    assert run["approvals"][-1]["target_stage"] == "scripting"
    assert run["approvals"][-1]["notes"] == "hook 1 overclaims"
