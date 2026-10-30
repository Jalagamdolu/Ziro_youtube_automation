"""Phase 1 done criterion: a stub run goes draft → all 3 gates → metrics_stub → done."""

from collections import Counter

from conftest import DISCLOSURE, approve, create, status

from app.graph.stages import ORDER


def test_stub_run_passes_all_gates_to_done(client, calls: Counter[str]) -> None:
    project_id = create(client)
    assert status(client, project_id)["status"] == "research_review"
    assert approve(client, project_id).status_code == 202
    assert status(client, project_id)["status"] == "script_review"
    assert approve(client, project_id).status_code == 202
    assert status(client, project_id)["status"] == "qa_review"
    assert approve(client, project_id, ai_disclosure=DISCLOSURE).status_code == 202

    run = status(client, project_id)
    assert run["status"] == "done"
    assert [e["to_state"] for e in run["events"]] == [*ORDER, "done"]
    assert all(count == 1 for count in calls.values()) and len(calls) == 8

    approvals = run["approvals"]
    assert [a["stage"] for a in approvals] == ["research_review", "script_review", "qa_review"]
    assert all(a["approver"] == "Hemu" and a["opened_at"] <= a["timestamp"] for a in approvals)
    assert approvals[2]["ai_disclosure"] == DISCLOSURE
    assert {a["type"] for a in run["artifacts"]} >= {"metrics.json", "publish_receipt.json"}
