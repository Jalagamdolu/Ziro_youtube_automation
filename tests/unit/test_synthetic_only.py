"""Synthetic-only (D-39): the machine makes the whole video. No run, however it was created, ever
waits on a recording; approving the script always goes straight to storyboarding → rendering.
The split layout's presenter zone (D-48) is a placeholder panel, never a wait for footage."""

import inspect

from conftest import SHORT_TOPIC, approve, create, status

import app.nodes.rendering as rendering_module
from app.core.contracts import Brief


def _path_after_script_review(client, project_id: str) -> list[str]:  # type: ignore[no-untyped-def]
    assert status(client, project_id)["status"] == "script_review"
    approve(client, project_id)
    run = status(client, project_id)
    assert run["status"] == "qa_review", run["jobs"][-1]
    moves = [(e["from_state"], e["to_state"]) for e in run["events"]]
    start = moves.index(("script_review", "storyboarding"))
    return [to for _, to in moves[start:]]


def test_ui_runs_never_wait_on_a_recording_even_if_asked(client) -> None:
    page = client.get("/").text
    assert 'name="presenter"' not in page and "present this video" not in page
    created = client.post("/ui/projects", data={"prompt": SHORT_TOPIC, "format": "short",
                                                "presenter": "true"}, follow_redirects=False)
    project_id = created.headers["location"].rsplit("/", 1)[1]
    assert "Record the presenter" not in client.get(f"/ui/projects/{project_id}").text
    assert _path_after_script_review(client, project_id) == ["storyboarding", "rendering",
                                                             "qa_review"]
    assert "Record the presenter" not in client.get(f"/ui/projects/{project_id}").text


def test_api_runs_never_wait_on_a_recording_even_if_asked(client) -> None:
    project_id = create(client, presenter=True)  # an old client still sending the flag
    assert _path_after_script_review(client, project_id) == ["storyboarding", "rendering",
                                                             "qa_review"]


def test_no_recording_upload_route_or_presenter_branch_remains(client) -> None:
    upload = client.post("/ui/projects/x/recording", files={"video": ("a.mp4", b"x")})
    assert upload.status_code in (404, 405)
    source = inspect.getsource(rendering_module).lower()
    assert "recording" not in source and "upload" not in source


def test_old_briefs_that_asked_for_a_presenter_still_load_as_synthetic() -> None:
    brief = Brief.model_validate({"topic": "What is RAG", "audience": "students",
                                  "learning_outcome": "RAG", "language": "en",
                                  "format": "short", "target_seconds": 30,
                                  "cta": "Explore AI learning at ziro.digital",
                                  "presenter": True})
    assert "presenter" not in brief.model_dump()
