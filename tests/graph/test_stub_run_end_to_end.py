"""A stub run goes draft → both gates (D-50) → metrics_stub → done."""

from collections import Counter

from conftest import DISCLOSURE, approve, create, publish, status

from app.graph.stages import ORDER


def test_stub_run_passes_all_gates_to_done(client, calls: Counter[str]) -> None:
    project_id = create(client)
    assert status(client, project_id)["status"] == "script_review"
    assert approve(client, project_id).status_code == 202
    assert status(client, project_id)["status"] == "qa_review"
    assert approve(client, project_id, ai_disclosure=DISCLOSURE).status_code == 202
    publish(project_id)  # D-64: a finished video publishes in its slot

    run = status(client, project_id)
    assert run["status"] == "done"
    assert [e["to_state"] for e in run["events"]] == [*ORDER, "done"]
    assert all(count == 1 for count in calls.values()) and len(calls) == 8

    approvals = run["approvals"]
    assert [a["stage"] for a in approvals] == ["script_review", "qa_review"]
    assert all(a["approver"] == "Dolender" for a in approvals)
    assert all(a["opened_at"] <= a["timestamp"] for a in approvals)
    assert approvals[1]["ai_disclosure"] == DISCLOSURE
    assert {a["type"] for a in run["artifacts"]} >= {"metrics.json", "publish_receipt.json"}
