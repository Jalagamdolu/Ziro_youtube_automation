"""Presenter videos (D-36): a real person's recording drives timing and layout; rendering waits
for the upload; the run page takes the upload and continues."""

import json

import pytest

from app.core.errors import FatalError
from app.nodes.rendering import (
    RECORDING,
    WAITING_FOR_RECORDING,
    rendering,
    scene_times,
    set_layouts,
)

SPOKEN = ["Why", "does", "it", "matter?", "A", "chatbot", "answers.", "Explore", "AI", "learning."]


def test_scenes_start_at_their_first_spoken_word() -> None:
    scenes = [{"text": "Why does it matter?"}, {"text": "A chatbot answers. [C2]"},
              {"text": "Explore AI learning."}]
    words = [{"text": t, "start": float(i), "end": i + 0.8} for i, t in enumerate(SPOKEN)]
    scene_times(scenes, words, clock=12.0)
    assert [(s["start"], s["end"]) for s in scenes] == [(0.0, 4.0), (4.0, 7.0), (7.0, 12.0)]

    scene_times(scenes, words[:3], clock=10.0)  # alignment lost words: share of the words
    assert [round(s["start"], 1) for s in scenes] == [0.0, 4.0, 7.0]


def test_layouts_open_on_the_presenter_split_cards_and_cut_to_photos() -> None:
    scenes = [{"visual_type": "comparison", "photo_query": "a"},
              {"visual_type": "definition_card", "photo_query": "b"},
              {"visual_type": "chat_bubble", "photo_query": "c"},
              {"visual_type": "title", "photo_query": None},
              {"visual_type": "end_card", "photo_query": None}]
    set_layouts(scenes)
    assert [s.get("layout") for s in scenes] == ["presenter", "split", "photo", "presenter",
                                                 None]
    assert [s["photo_query"] for s in scenes] == [None, None, "c", None, None]  # cut-aways only


def test_rendering_waits_for_the_recording() -> None:
    class Store:
        def exists(self, key: str) -> bool:
            return False

    class Ctx:
        project_id, storage = "p", Store()

        def read_json(self, stage: str, name: str) -> object:
            from app.adapters.llm import FixtureLLM
            from app.adapters.research import FixtureResearch
            from app.core.contracts import Brief, ContentPackage, Hook

            brief = Brief(topic="What makes an AI agent different from a chatbot?", audience="a",
                          learning_outcome="o", language="en", format="short",
                          target_seconds=60, cta="Explore AI learning at ziro.digital",
                          presenter=True)
            claims = FixtureResearch().find_claims(brief)
            d = FixtureLLM().write_package(brief, claims, None)
            return json.loads(ContentPackage(
                brief=brief, claims=claims, script=d.script, hooks=[
                    Hook(text=h.text, score=1, explanation=h.explanation) for h in d.hooks],
                top_hooks=[d.hooks[0].text, d.hooks[1].text], titles=d.titles,
                top_titles=d.titles[:3], thumbnail_text=d.thumbnail_text,
                description=d.description, tags=d.tags, target_queries=d.target_queries,
                chapters=d.chapters).model_dump_json())

    with pytest.raises(FatalError, match="waiting for the presenter's recording"):
        rendering(Ctx())  # type: ignore[arg-type]


def test_presenter_run_shows_the_teleprompter_and_upload_continues_rendering(
        client, monkeypatch) -> None:
    from conftest import SHORT_TOPIC, approve, status

    import app.nodes as nodes
    from app.adapters import storage
    from app.nodes import stubs

    def waits_for_recording(ctx):  # type: ignore[no-untyped-def]
        if not ctx.storage.exists(RECORDING.format(ctx.project_id)):
            raise FatalError(WAITING_FOR_RECORDING)
        return stubs.rendering(ctx)

    monkeypatch.setitem(nodes.FUNCS, "rendering", waits_for_recording)
    created = client.post("/ui/projects", data={"prompt": SHORT_TOPIC, "format": "short",
                                                "presenter": "true"}, follow_redirects=False)
    project_id = created.headers["location"].rsplit("/", 1)[1]
    approve(client, project_id)  # research_review

    page = client.get(f"/ui/projects/{project_id}").text
    assert "Record the presenter" in page and "Your chatbot answers. Why can" in page
    approve(client, project_id)  # script_review, before any upload
    run = status(client, project_id)
    assert run["status"] == "failed"
    assert "waiting for the presenter" in run["jobs"][-1]["error_message"]
    assert "Upload the recording" in client.get(f"/ui/projects/{project_id}").text

    client.post(f"/ui/projects/{project_id}/recording",
                files={"video": ("take1.mp4", b"MP4DATA", "video/mp4")},
                data={"reviewer": "Dolender"})
    assert storage.get().read(RECORDING.format(project_id)) == b"MP4DATA"
    assert status(client, project_id)["status"] == "qa_review"


def test_shots_cut_about_every_three_seconds_at_word_boundaries() -> None:
    from app.nodes.rendering import plan_shots

    words = [{"text": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.45} for i in range(24)]
    scenes = [{"visual_type": "comparison", "start": 0.0, "end": 4.0, "layout": "presenter"},
              {"visual_type": "definition_card", "start": 4.0, "end": 11.0, "layout": "split",
               "capture": "capture_S2.png"},
              {"visual_type": "end_card", "start": 11.0, "end": 13.0}]
    plan_shots(scenes, words, presenter=True)
    first, card, end = (s["shots"] for s in scenes)
    assert [s["kind"] for s in first] == ["presenter"]  # opens on the presenter's face
    assert [s["kind"] for s in card] == ["capture", "split"]  # source page, then the card
    assert [s["card"] for s in card] == [False, True]
    assert all(round(s["end"] % 0.5, 2) == 0.45 for s in card[:-1])  # cut where a word ends
    assert end == [{"start": 11.0, "end": 13.0, "kind": "end", "card": True}]


def test_narrated_videos_alternate_two_camera_moves_on_the_photo() -> None:
    from app.nodes.rendering import plan_shots

    scenes = [{"visual_type": "title", "start": 0.0, "end": 9.0, "photo": "photo_S1.jpg"}]
    plan_shots(scenes, [], presenter=False)
    assert [s["kind"] for s in scenes[0]["shots"]] == ["photo", "photo_alt", "photo"]
    assert all(s["card"] for s in scenes[0]["shots"])
