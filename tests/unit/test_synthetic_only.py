"""Synthetic-only (D-39): the machine makes the whole video. No run, however it was created, ever
waits on a recording; approving the script always goes straight to storyboarding → rendering."""

import inspect

from conftest import SHORT_TOPIC, approve, create, status

import app.nodes.rendering as rendering_module
from app.core.contracts import Brief
from app.nodes.rendering import plan_shots


def _path_after_script_review(client, project_id: str) -> list[str]:  # type: ignore[no-untyped-def]
    approve(client, project_id)  # research_review
    assert status(client, project_id)["status"] == "script_review"
    approve(client, project_id)  # script_review
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
    assert "presenter" not in source and "recording" not in source


def test_old_briefs_that_asked_for_a_presenter_still_load_as_synthetic() -> None:
    brief = Brief.model_validate({"topic": "What is RAG", "audience": "students",
                                  "learning_outcome": "RAG", "language": "en",
                                  "format": "short", "target_seconds": 30,
                                  "cta": "Explore AI learning at ziro.digital",
                                  "presenter": True})
    assert "presenter" not in brief.model_dump()


def test_shots_cut_about_every_three_seconds_at_word_boundaries() -> None:
    words = [{"text": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.45} for i in range(24)]
    scenes = [{"visual_type": "definition_card", "start": 4.0, "end": 11.0,
               "capture": "capture_S2.png", "photo": "photo_S2.jpg"},
              {"visual_type": "end_card", "start": 11.0, "end": 13.0}]
    plan_shots(scenes, words)
    card, end = (s["shots"] for s in scenes)
    assert [s["kind"] for s in card] == ["capture", "photo"]  # source page, then the photo
    assert [s["card"] for s in card] == [False, True]
    assert all(round(s["end"] % 0.5, 2) == 0.45 for s in card[:-1])  # cut where a word ends
    assert end == [{"start": 11.0, "end": 13.0, "kind": "end", "card": True}]


def test_photo_scenes_alternate_two_camera_moves() -> None:
    scenes = [{"visual_type": "title", "start": 0.0, "end": 9.0, "photo": "photo_S1.jpg"}]
    plan_shots(scenes, [])
    assert [s["kind"] for s in scenes[0]["shots"]] == ["photo", "photo_alt", "photo"]
    assert all(s["card"] for s in scenes[0]["shots"])
