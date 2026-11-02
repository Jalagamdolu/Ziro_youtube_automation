"""Review UI (§8): the three gate screens, form decisions, run log, file serving and the bundle."""

import html
import io
import json
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


def test_first_visit_is_the_prompt_then_the_runs_list(client) -> None:
    home = client.get("/").text
    assert 'name="prompt"' in home and "All runs" not in home
    project_id = _start(client)
    runs = client.get("/").text
    assert "All runs" in runs and f"/ui/projects/{project_id}" in runs and "$0.0000" in runs
    assert 'name="prompt"' in client.get("/new").text


def test_stage_table_shows_the_gate_waiting_and_approve_all_advances(client) -> None:
    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "<h2>Stages</h2>" in page and "waiting for you" in page
    assert "Approve all 4 claims as-is" in page
    assert _decide(client, project_id, decision="approve", reviewer="Dolender") is None
    run = status(client, project_id)
    assert run["status"] == "script_review"
    assert run["approvals"][0]["claim_edits"] == {"removed": [], "edited": {}}


def test_hand_edit_from_the_browser_goes_through_every_check(client) -> None:
    from app.adapters import storage
    from app.nodes import human_edit

    project_id = _start(client)
    _decide(client, project_id, **_keep_all())
    page = client.get(f"/ui/projects/{project_id}").text
    assert "Edit the script myself" in page
    original = html.unescape(page.split('aria-label="Editable script package">')[1]
                             .split("</textarea>")[0])

    hype = original.replace("AI Agent vs Chatbot for Students", "Boost Your Chatbot Skills")
    edited = client.post(f"/ui/projects/{project_id}/edit",
                         data={"text": hype, "reviewer": "Asha"}, follow_redirects=False)
    assert edited.status_code == 303
    run = status(client, project_id)
    assert run["status"] == "failed" and "'Boost'" in run["jobs"][-1]["error_message"]
    assert run["approvals"][-1]["notes"].startswith("Hand-edited script submitted by Asha")
    page = html.unescape(client.get(f"/ui/projects/{project_id}").text)
    assert "!! RULE: packaging claims 'Boost'" in page  # the failed edit comes back annotated

    client.post(f"/ui/projects/{project_id}/edit", data={"text": original, "reviewer": "Asha"})
    run = status(client, project_id)
    assert run["status"] == "script_review"
    trail = next(a for a in run["artifacts"] if a["type"] == "human_edit.json")
    assert json.loads(storage.get().read(trail["storage_path"]))["edited_by"] == "Asha"
    assert not storage.get().exists(human_edit.KEY.format(project_id))  # used once


def test_finished_run_shows_player_downloads_and_cost(client) -> None:
    project_id = _start(client)
    _decide(client, project_id, **_keep_all())
    _decide(client, project_id, decision="approve", reviewer="Dolender")
    _decide(client, project_id, decision="approve", reviewer="Dolender", ai_synthetic="yes",
            ai_reason="synthetic narration voice")
    page = client.get(f"/ui/projects/{project_id}").text
    assert "Your video" in page and "<video" in page
    for label in ("Video (MP4)", "Captions (SRT)", "Thumbnail", "Claims",
                  "Publish receipt (mock)", "Everything (ZIP)"):
        assert label in page, label
    assert "<h3>Cost</h3>" in page and "Edit the script myself" not in page


def test_failed_scripting_offers_the_last_draft_flagged_and_a_fix_reaches_review(
        client, monkeypatch) -> None:
    from app.adapters import llm

    class Hype(llm.FixtureLLM):
        def write_package(self, brief, claims, notes):  # type: ignore[no-untyped-def]
            good = super().write_package(brief, claims, notes)
            return good.model_copy(update={"titles": ["Boost Your Chatbot Skills"]
                                           + good.titles[1:]})

    monkeypatch.setattr(llm, "get", lambda stage="default": Hype())
    project_id = _start(client)
    _decide(client, project_id, **_keep_all())
    assert status(client, project_id)["status"] == "failed"  # the model never passed

    page = html.unescape(client.get(f"/ui/projects/{project_id}").text)
    assert "Edit the last draft myself" in page
    draft = page.split('aria-label="Editable script package">')[1].split("</textarea>")[0]
    assert "Boost Your Chatbot Skills\n!! RULE: packaging claims 'Boost'" in draft
    assert "=== HOOKS ===" in draft and "=== DESCRIPTION ===" in draft  # the whole package

    fixed = draft.replace("Boost Your Chatbot Skills", "AI Agent vs Chatbot for Students")
    client.post(f"/ui/projects/{project_id}/edit", data={"text": fixed, "reviewer": "Dolender"})
    run = status(client, project_id)
    assert run["status"] == "script_review"
    assert any(a["type"] == "human_edit.json" for a in run["artifacts"])
