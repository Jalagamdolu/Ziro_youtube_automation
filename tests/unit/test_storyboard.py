"""Storyboard: each [ON SCREEN] beat becomes a scene; definition cards carry approved claims."""

import json

from app.adapters.llm import FixtureLLM
from app.adapters.research import FixtureResearch
from app.core.contracts import Brief, ContentPackage, Hook
from app.nodes.storyboarding import storyboarding, visual_type

BRIEF = Brief(topic="What makes an AI agent different from a chatbot?", audience="a",
              learning_outcome="o", language="en", format="short", target_seconds=60,
              cta="Explore AI learning at ziro.digital")


class _Ctx:
    def __init__(self, package: ContentPackage) -> None:
        self.package = package

    def read_json(self, stage: str, name: str) -> object:
        return json.loads(self.package.model_dump_json())


def test_fixture_script_becomes_scenes_with_sourced_definition_cards() -> None:
    claims = FixtureResearch().find_claims(BRIEF)
    draft = FixtureLLM().write_package(BRIEF, claims, None)
    package = ContentPackage(
        brief=BRIEF, claims=claims, script=draft.script,
        hooks=[Hook(text=h.text, score=1, explanation=h.explanation) for h in draft.hooks],
        top_hooks=[draft.hooks[0].text, draft.hooks[1].text], titles=draft.titles,
        top_titles=draft.titles[:3], thumbnail_text=draft.thumbnail_text,
        description=draft.description, tags=draft.tags, target_queries=draft.target_queries,
        chapters=draft.chapters)
    scenes = json.loads(storyboarding(_Ctx(package))["scenes.json"])  # type: ignore[arg-type]

    assert len(scenes) == draft.script.count("[ON SCREEN")
    assert all(s["text"] for s in scenes)
    cards = [s for s in scenes if s["visual_type"] == "definition_card"]
    assert [c["props"]["headline"] for c in cards] == ["What is a chatbot?", "What are AI agents?"]
    assert cards[0]["props"]["definition"] == claims[1].claim  # C2, approved wording
    assert cards[0]["props"]["source"] == "IBM"

    by_type = {s["visual_type"]: s["props"] for s in scenes}
    assert by_type["comparison"].items() >= {"left": "Chatbot", "right": "Agent",
                                             "between": "?"}.items()
    assert by_type["chat_bubble"]["message"] == "When is my exam?"
    assert by_type["flow"]["steps"] == ["search", "read", "shortlist", "calendar"]
    assert by_type["flow"]["label"] == "example"
    assert by_type["quote_card"]["definition"] == f"“{claims[0].quote}”"  # C1, verified quote
    assert by_type["checklist"]["items"] == ["Only talks: chatbot",
                                             "Pursues a goal, uses tools, acts: agent"]
    assert by_type["end_card"]["url"] == "ziro.digital"


def test_unknown_beats_fall_back_to_title() -> None:
    assert visual_type("a student's project board") == "title"
    assert visual_type('quote card, source: Anthropic') == "quote_card"
