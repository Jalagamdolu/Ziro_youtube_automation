"""Review UI (§8): the three gate screens, form decisions, run log, file serving and the bundle."""

import io
import zipfile
from urllib.parse import parse_qs, urlparse

from conftest import SHORT_TOPIC, status


def _start(client) -> str:
    response = client.post("/ui/projects", data={"prompt": SHORT_TOPIC, "format": "short"},
                           follow_redirects=False)
    assert response.status_code == 303
    return response.headers["location"].rsplit("/", 1)[1]


def _decide(client, project_id: str, **form: str):
    response = client.post(f"/ui/projects/{project_id}/decide", data=form,
                           follow_redirects=False)
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query).get("error", [None])[0]


def _keep_all(**extra: str) -> dict[str, str]:
    return {"decision": "approve", "reviewer": "Dolender",
            **{f"action_C{i}": "keep" for i in range(1, 5)}, **extra}


def test_research_review_screen_and_per_claim_edit(client) -> None:
    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "Research review" in page
    assert 'href="https://www.ibm.com/think/topics/chatbots"' in page
    assert "A chatbot is a software application that communicates" in page  # the quote

    edited = "IBM: a chatbot is software that talks with people by text or voice."
    assert _decide(client, project_id, **_keep_all(text_C2=edited)) is None
    run = status(client, project_id)
    assert run["status"] == "script_review"
    assert run["approvals"][0]["claim_edits"] == {"removed": [], "edited": {"C2": edited}}


def test_script_and_qa_screens_through_to_done(client) -> None:
    project_id = _start(client)
    _decide(client, project_id, **_keep_all())

    page = client.get(f"/ui/projects/{project_id}").text
    assert "Five hooks" in page and page.count("top 2</span>") == 2
    assert page.count("top 3</span>") == 3 and "TALK OR DO?" in page
    _decide(client, project_id, decision="approve", reviewer="Dolender")

    page = client.get(f"/ui/projects/{project_id}").text
    assert "<video" in page and "AI disclosure (required)" in page
    error = _decide(client, project_id, decision="approve", reviewer="Dolender")
    assert error and "ai_disclosure" in error
    assert status(client, project_id)["status"] == "qa_review"

    assert _decide(client, project_id, decision="approve", reviewer="Dolender",
                   ai_synthetic="yes", ai_reason="synthetic narration voice") is None
    run = status(client, project_id)
    assert run["status"] == "done"
    assert run["approvals"][-1]["ai_disclosure"] == {"synthetic": True,
                                                     "reason": "synthetic narration voice"}
    page = client.get(f"/ui/projects/{project_id}").text
    assert "State timeline" in page and "Run log" in page and "mock_published" in page


def test_reject_needs_notes_and_shows_the_error(client) -> None:
    project_id = _start(client)
    error = _decide(client, project_id, decision="reject", reviewer="Dolender",
                    target="researching", notes="")
    assert error and "notes" in error
    assert status(client, project_id)["approvals"] == []
    assert "Not done:" in client.get(f"/ui/projects/{project_id}?error=x").text


def test_files_only_serve_registered_artifacts(client) -> None:
    project_id = _start(client)
    claims = next(a for a in status(client, project_id)["artifacts"] if a["type"] == "claims.json")
    files = f"/ui/projects/{project_id}/files"
    assert client.get(f"{files}/{claims['storage_path']}").status_code == 200
    assert client.get(f"{files}/{project_id}/request.json").status_code == 404  # not registered
    assert client.get(f"{files}/../../etc/passwd").status_code == 404


def test_download_bundle_has_latest_artifacts(client) -> None:
    project_id = _start(client)
    response = client.get(f"/ui/projects/{project_id}/bundle.zip")
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert {"draft/brief.json", "researching/claims.json"} <= set(names)


def test_live_view_reloads_on_any_new_transition(client) -> None:
    project_id = _start(client)
    events = len(status(client, project_id)["events"])
    stale = client.get(f"/ui/projects/{project_id}/live", params={"seen": events - 1})
    assert stale.headers.get("HX-Redirect") == f"/ui/projects/{project_id}"
    same = client.get(f"/ui/projects/{project_id}/live", params={"seen": events})
    assert "HX-Redirect" not in same.headers


def test_decided_gate_is_hidden_until_the_run_moves(client) -> None:
    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}", params={"submitted": "research_review"})
    assert "Decision recorded" in page.text and "Approve claims" not in page.text
