"""Split layout (D-48) and the shot planner (D-49): the timeline the Remotion template draws."""

import importlib
from typing import Any

import pytest

from app.adapters import llm
from app.nodes.rendering import echo_track, pacing, plan_shots

storyboarding = importlib.import_module("app.nodes.storyboarding")  # app.nodes re-exports it


def timed(start: float, lengths: list[float], texts: list[str] | None = None) -> list[dict]:
    out, clock = [], start
    for i, length in enumerate(lengths):
        out.append({"text": (texts or [f"s{i}"] * len(lengths))[i], "start": clock,
                    "end": clock + length})
        clock += length + 0.15
    return out


def scenes() -> list[dict[str, Any]]:
    hook = {"id": "S1", "section": "Hook", "visual_type": "comparison", "start": 0.0, "end": 2.4,
            "timed": timed(0.0, [2.2]), "echo": ["chatbot act"]}
    body = {"id": "S2", "section": "Example", "visual_type": "definition_card", "start": 2.8,
            "end": 14.0, "capture": "capture_S2.png", "photo": "photo_S2.jpg",
            "timed": timed(2.8, [4.5, 2.5, 3.6]), "echo": ["software", "goal", "tools"],
            "pop": {"sentence": 1, "text": "It pursues a goal", "punch": ["goal"]}}
    plain = {"id": "S3", "section": "Takeaway", "visual_type": "checklist", "start": 14.35,
             "end": 23.0, "timed": timed(14.35, [8.4]), "echo": ["test"]}
    cta = {"id": "S4", "section": "CTA", "visual_type": "end_card", "start": 23.35, "end": 28.0,
           "timed": timed(23.35, [1.8, 2.2]), "echo": ["which", "explore"]}
    return [hook, body, plain, cta]


def words() -> list[dict[str, float]]:
    return [{"text": "w", "start": t / 4, "end": t / 4 + 0.2} for t in range(0, 112)]


def test_hook_pop_and_close_are_full_screen_the_body_is_split() -> None:
    planned = scenes()
    plan_shots(planned, words())
    hook, body, plain, cta = (s["shots"] for s in planned)
    assert {(s["layout"], s["kind"]) for s in hook} <= {("full", "presenter"),
                                                       ("full", "presenter_alt")}
    assert [s["kind"] for s in body if s["layout"] == "full"] == ["pop"]
    assert all(s["layout"] == "split" for s in plain)
    assert [s["kind"] for s in cta] == ["presenter", "end"]  # the question, then the end card
    assert cta[-1]["start"] == planned[3]["timed"][-1]["start"]


def test_one_source_proof_per_video_then_photo_and_card_alternate() -> None:
    planned = scenes()
    planned[2]["capture"] = "capture_S3.png"  # a second capture is never shown
    plan_shots(planned, words())
    kinds = [s["kind"] for scene in planned for s in scene["shots"]]
    assert kinds.count("capture") == 1 and kinds.index("capture") < kinds.index("pop")
    split = [s["kind"] for s in planned[1]["shots"] if s["layout"] == "split"]
    assert split[0] == "capture" and set(split[1:]) <= {"photo", "card"}
    assert {s["kind"] for s in planned[2]["shots"]} <= {"card", "card_alt"}  # no photo there
    assert all(s["card"] == (s["kind"] in ("card", "card_alt"))
               for scene in planned for s in scene["shots"])


def test_picture_changes_every_two_to_four_seconds() -> None:
    planned = scenes()
    plan_shots(planned, words())
    report = pacing(planned)
    assert report["ok"] and report["longest_s"] <= 4.0
    shots = [s for scene in planned for s in scene["shots"]]
    pairs = zip(shots, shots[1:], strict=False)
    assert all(a["end"] == pytest.approx(b["start"]) for a, b in pairs)  # no gaps


def test_pacing_qa_fails_a_long_hold() -> None:
    planned = [{"id": "S1", "section": "Example", "visual_type": "title", "start": 0, "end": 9,
                "shots": [{"start": 0, "end": 9, "kind": "card", "layout": "split"}]}]
    assert pacing(planned)["ok"] is False


def test_echo_skips_the_pop_and_the_end_card_line_and_brands_every_third() -> None:
    planned = scenes()
    track = echo_track(planned)
    assert [e["text"] for e in track] == ["chatbot act", "software", "tools", "test", "which"]
    assert [e["brand"] for e in track] == [False, False, True, False, False]


CLAIMS: list = []


def planner_scenes() -> list[dict[str, Any]]:
    return [{"id": "S1", "section": "Hook", "visual_type": "comparison",
             "text": "Your chatbot answers. Why can't it act?"},
            {"id": "S2", "section": "Example", "visual_type": "flow",
             "text": "First it searches your files. [C2] Then it writes the answer. [C3]"},
            {"id": "S3", "section": "CTA", "visual_type": "end_card",
             "text": "Explore AI learning at ziro.digital."}]


class StubPlanner:
    calls: list = []

    def __init__(self, reply: Any) -> None:
        self.reply = reply

    def json(self, system: str, prompt: str, schema: Any = None) -> Any:
        return self.reply


def test_planner_proposals_are_kept_only_when_the_narration_says_them(monkeypatch) -> None:
    monkeypatch.setattr(llm, "planner_chat", lambda project_id: StubPlanner({
        "echoes": ["chatbot answers", "it act", "boost your files", "writes answer",
                   "ziro.digital"],
        "pops": [{"index": 3, "text": "it writes the answer", "punch": ["writes"]},
                 {"index": 0, "text": "Your chatbot answers", "punch": ["answers"]}]}))
    planned = planner_scenes()
    storyboarding.plan_beats("p1", planned, CLAIMS)
    assert planned[0]["echo"] == ["chatbot answers", "it act"]
    assert planned[1]["echo"][0] != "boost your files"  # never said, and an outcome word
    assert planned[1]["echo"][1] == "writes answer"
    assert planned[1]["pop"] == {"sentence": 1, "text": "it writes the answer",
                                 "punch": ["writes"]}
    assert "pop" not in planned[0]  # the Hook is the presenter's, not a text pop


def test_without_a_planner_the_code_plans_one_pop_and_every_echo(monkeypatch) -> None:
    monkeypatch.setattr(llm, "planner_chat", lambda project_id: None)
    planned = planner_scenes()
    storyboarding.plan_beats("p1", planned, CLAIMS)
    assert [len(s["echo"]) for s in planned] == [2, 2, 1]
    assert planned[1]["echo"][0] == "First searches files"
    pops = [s["pop"] for s in planned if "pop" in s]
    assert len(pops) == 1 and pops[0]["text"] == "First it searches your files."
    assert pops[0]["punch"] == ["searches"]


def test_presenter_zone_is_sirs_place_and_the_logo_is_only_on_the_end_card() -> None:
    import inspect
    from pathlib import Path

    rendering = importlib.import_module("app.nodes.rendering")
    src = Path(rendering.__file__).resolve().parents[3] / "templates" / "remotion" / "src"
    presenter = (src / "Presenter.tsx").read_text(encoding="utf-8")
    assert "presenter — sir" in presenter and ".png" not in presenter  # D-57: no brand image
    assert "wordmark" not in inspect.getsource(rendering).lower()
    uses_logo = [f.name for f in src.rglob("*.tsx") if "props as Record" in f.read_text(
        encoding="utf-8") and "logo" in f.read_text(encoding="utf-8")]
    assert uses_logo == ["EndCard.tsx"]  # D-35: the official logo only on the end card
