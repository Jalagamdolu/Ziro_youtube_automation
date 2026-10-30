"""T08: reject → no upload; approve → export and mock publish only."""

from collections import Counter

from conftest import DISCLOSURE, approve, reject, run_to_qa_review, status


def test_reject_at_qa_review_never_publishes(client, calls: Counter[str]) -> None:
    project_id = run_to_qa_review(client)
    assert reject(client, project_id, "rendering").status_code == 202

    run = status(client, project_id)
    assert run["status"] == "qa_review"  # re-rendered and back at the gate
    assert calls["export_ready"] == calls["mock_published"] == 0
    assert not any(a["stage"] == "mock_published" for a in run["artifacts"])


def test_approve_enables_mock_publish_only(client) -> None:
    project_id = run_to_qa_review(client)
    assert approve(client, project_id, ai_disclosure=DISCLOSURE).status_code == 202

    run = status(client, project_id)
    assert run["status"] == "done"
    receipt = [a for a in run["artifacts"] if a["type"] == "publish_receipt.json"]
    assert len(receipt) == 1


def test_decisions_rejected_outside_a_gate(client) -> None:
    project_id = run_to_qa_review(client)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert approve(client, project_id).status_code == 409


def test_qa_approval_requires_ai_disclosure(client) -> None:
    project_id = run_to_qa_review(client)
    assert approve(client, project_id).status_code == 422
    assert status(client, project_id)["status"] == "qa_review"


def test_reject_requires_valid_target_and_notes(client) -> None:
    project_id = run_to_qa_review(client)
    assert reject(client, project_id, "draft").status_code == 422
    assert reject(client, project_id, "rendering", notes=" ").status_code == 422
    assert [a["stage"] for a in status(client, project_id)["approvals"]] == [
        "research_review", "script_review"]  # nothing recorded for the invalid rejects
