"""T04: five distinct hooks, the brief §07 structure and timings, one CTA."""

import pytest

from app.adapters.llm import FixtureLLM
from app.adapters.research import FixtureResearch
from app.core.contracts import Brief
from app.nodes.script_checks import shape_problems

BRIEF = Brief(topic="What makes an AI agent different from a chatbot?", audience="Indian students",
              learning_outcome="o", language="en", format="short", target_seconds=60,
              cta="Explore AI learning at ziro.digital")


def _fixture_script() -> str:
    return FixtureLLM().write_package(BRIEF, FixtureResearch().find_claims(BRIEF), None).script


def test_fixture_package_has_five_distinct_hooks_and_valid_shape() -> None:
    draft = FixtureLLM().write_package(BRIEF, FixtureResearch().find_claims(BRIEF), None)
    assert len({h.text for h in draft.hooks}) == 5
    assert shape_problems(draft.script, BRIEF) == []


@pytest.mark.parametrize("break_it,expected", [
    (lambda s: s.replace("## Relevance", "## Why"), "sections must be"),
    (lambda s: s.replace("Why does your chatbot stop before work?",
                         "Why does your chatbot always stop right before the real work begins?"),
     "hook takes"),
    (lambda s: s.replace("## Takeaway", "## Takeaway\nExplore AI learning at ziro.digital."),
     "CTA must appear exactly once"),
    (lambda s: s + ("More words to stretch the runtime. " * 30), "runtime"),
    (lambda s: s.replace('[ON SCREEN: Ziro logo and "ziro.digital"]', ""), "no [ON SCREEN"),
])
def test_shape_violations_are_caught(break_it, expected: str) -> None:
    problems = shape_problems(break_it(_fixture_script()), BRIEF)
    assert any(expected in p for p in problems), problems
