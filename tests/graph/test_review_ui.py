"""Review UI (§8): the two gate screens (D-50), form decisions, run log, file serving and the
bundle."""

import html
import io
import json
import zipfile
from urllib.parse import parse_qs, urlparse

from conftest import SHORT_TOPIC, publish, status


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



def test_script_review_is_beat_by_beat_with_each_source_beside_its_line(client) -> None:
    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "Your script review" in page and "Research review" not in page
    assert '<h3 class="beat">Hook</h3>' in page  # beat by beat (D-69)
    fact = page[page.index("A chatbot is a software application that communicates"):]
    fact = fact[:fact.index('<div class="line')]  # this line and what sits beside it
    assert 'href="https://www.ibm.com/think/topics/chatbots"' in fact and "<q>" in fact
    assert "definition</span>" in page or "other</span>" in page  # kind labels
    assert "✓ Approve" in page and "openPanel('edit')" in page and "openPanel('regenerate')" in page


def test_script_and_qa_screens_through_to_done(client) -> None:
    project_id = _start(client)

    page = client.get(f"/ui/projects/{project_id}").text
    assert "Hooks, titles and description" in page and page.count("top 2</span>") == 2
    assert page.count("top 3</span>") == 3 and "TALK OR DO?" in page
    _decide(client, project_id, decision="approve", reviewer="Dolender")

    page = client.get(f"/ui/projects/{project_id}").text
    assert "<video" in page and "AI disclosure (required)" in page
    error = _decide(client, project_id, decision="approve", reviewer="Dolender")
    assert error and "ai_disclosure" in error
    assert status(client, project_id)["status"] == "qa_review"

    assert _decide(client, project_id, decision="approve", reviewer="Dolender",
                   ai_synthetic="yes", ai_reason="synthetic narration voice") is None
    publish(project_id)
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
    page = client.get(f"/ui/projects/{project_id}", params={"submitted": "script_review"})
    assert "Decision recorded" in page.text and "Approve script and package" not in page.text


def test_home_is_the_library_and_every_video_is_a_card(client) -> None:
    home = client.get("/").text
    assert "<h1>Library</h1>" in home and "Nothing here yet" in home
    for place in ('href="/new"', 'href="/library"', 'href="/planner"'):  # the sidebar (D-69)
        assert place in home
    project_id = _start(client)
    cards = client.get("/").text
    assert f"/ui/projects/{project_id}" in cards and "Needs your review (script)" in cards
    assert "Needs you · 1" in cards  # the sidebar badge
    new = client.get("/new").text
    assert 'name="prompt"' in new and 'name="keywords"' in new and 'name="guidelines"' in new
    assert [f'value="{s}"' in new for s in (30, 40, 50, 60)] == [True] * 4
    assert 'name="format"' not in new  # Shorts only until long templates exist


def test_stage_table_shows_the_gate_waiting_and_approve_all_advances(client) -> None:
    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "<h2>Stages</h2>" in page and "waiting for you" in page
    assert _decide(client, project_id, decision="approve", reviewer="someone else") is None
    run = status(client, project_id)
    assert run["status"] == "qa_review"
    assert run["approvals"][0]["approver"] == "Dolender"  # the logged-in user, not the form


def test_hand_edit_from_the_browser_goes_through_every_check(client) -> None:
    from app.adapters import storage
    from app.nodes import human_edit

    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "Edit before approving" in page
    # one decision bar: Approve, Edit (opens the edit panel) and Send back (D-63)
    assert "✓ Approve" in page and "openPanel('edit')" in page
    assert "openPanel('reject')" in page and "Submit my edit through all checks" in page
    original = html.unescape(page.split('aria-label="Editable script package">')[1]
                             .split("</textarea>")[0])

    hype = original.replace("AI Agent vs Chatbot for Students", "Boost Your Chatbot Skills")
    edited = client.post(f"/ui/projects/{project_id}/edit",
                         data={"text": hype, "reviewer": "Dolender"}, follow_redirects=False)
    assert edited.status_code == 303
    run = status(client, project_id)
    assert run["status"] == "failed" and "'Boost'" in run["jobs"][-1]["error_message"]
    assert run["approvals"][-1]["notes"].startswith("Hand-edited script submitted by Dolender")
    page = html.unescape(client.get(f"/ui/projects/{project_id}").text)
    assert "!! RULE: packaging claims 'Boost'" in page  # the failed edit comes back annotated
    assert not storage.get().exists(human_edit.KEY.format(project_id))  # retry won't reuse it

    client.post(f"/ui/projects/{project_id}/edit", data={"text": original, "reviewer": "Dolender"})
    run = status(client, project_id)
    assert run["status"] == "script_review"
    trail = next(a for a in run["artifacts"] if a["type"] == "human_edit.json")
    assert json.loads(storage.get().read(trail["storage_path"]))["edited_by"] == "Dolender"
    assert not storage.get().exists(human_edit.KEY.format(project_id))  # used once


def test_finished_run_shows_player_downloads_and_cost(client) -> None:
    project_id = _start(client)
    _decide(client, project_id, decision="approve", reviewer="Dolender")
    _decide(client, project_id, decision="approve", reviewer="Dolender", ai_synthetic="yes",
            ai_reason="synthetic narration voice")
    publish(project_id)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "✓ Published (mock)" in page and "<video" in page
    for label in ("Video (MP4)", "Captions (SRT)", "Thumbnail", "Claims",
                  "Publish receipt", "Everything (ZIP)"):
        assert label in page, label
    assert "<h3>Cost</h3>" in page and "Edit before approving" not in page


def test_failed_scripting_offers_the_last_draft_flagged_and_a_fix_reaches_review(
        client, monkeypatch) -> None:
    from app.adapters import llm

    class Hype(llm.FixtureLLM):
        def write_package(self, brief, claims, notes):  # type: ignore[no-untyped-def]
            good = super().write_package(brief, claims, notes)
            return good.model_copy(update={"titles": ["Boost Your Chatbot Skills"]
                                           + good.titles[1:]})

    monkeypatch.setattr(llm, "get", lambda *args, **kwargs: Hype())
    project_id = _start(client)
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


def test_a_second_different_hand_edit_is_not_served_from_the_cache(client) -> None:
    project_id = _start(client)
    page = client.get(f"/ui/projects/{project_id}").text
    original = html.unescape(page.split('aria-label="Editable script package">')[1]
                             .split("</textarea>")[0])
    for n, tags in enumerate(["first edit tag", "second edit tag"], 1):
        edited = original.replace("=== TAGS ===\n", f"=== TAGS ===\n{tags}\n")
        client.post(f"/ui/projects/{project_id}/edit", data={"text": edited})
        run = status(client, project_id)
        assert run["status"] == "script_review"
        jobs = [j["status"] for j in run["jobs"] if j["stage"] == "scripting"]
        assert jobs[-1] == "succeeded" and len(jobs) == n + 1  # ran, not "cached"
        assert tags in json.loads(storage_package(run))["tags"]


def storage_package(run: dict) -> str:  # type: ignore[type-arg]
    from app.adapters import storage

    key = [a["storage_path"] for a in run["artifacts"] if a["type"] == "content_package.json"
           and not a["stale"]][-1]
    return storage.get().read(key).decode("utf-8")
