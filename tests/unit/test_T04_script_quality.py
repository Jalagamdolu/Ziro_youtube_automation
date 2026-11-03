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
    (lambda s: s.replace("Your chatbot answers. Why can't it act?",
                         "Your chatbot answers questions all day, so why can't it act for you?"),
     "hook takes"),
    (lambda s: s.replace("## Takeaway", "## Takeaway\nExplore AI learning at ziro.digital."),
     "CTA must appear exactly once"),
    (lambda s: s + ("More words to stretch the runtime. " * 30), "runtime"),
    (lambda s: s.replace('[ON SCREEN: Ziro logo and "ziro.digital"]', ""), "no [ON SCREEN"),
])
def test_shape_violations_are_caught(break_it, expected: str) -> None:
    problems = shape_problems(break_it(_fixture_script()), BRIEF)
    assert any(expected in p for p in problems), problems


def test_any_requested_length_within_tolerance() -> None:
    """D-35: the target drives the runtime check (±15%), e.g. a 30 s Short."""
    import pytest
    from pydantic import ValidationError

    from app.core.contracts import Brief
    from app.nodes.script_checks import runtime, shape_problems

    brief = Brief(topic="t", audience="a", learning_outcome="o", language="en", format="short",
                  target_seconds=30, cta="Explore AI learning at ziro.digital")
    assert runtime(brief) == (26, 34)
    with pytest.raises(ValidationError):
        Brief.model_validate(brief.model_dump() | {"target_seconds": 10})

    def script(example_words: int) -> str:
        return ("## Hook\n[ON SCREEN: \"Why?\"]\nWhy does this matter?\n"
                "## Relevance\n[ON SCREEN: \"You\"]\nIf you build apps, this matters to you.\n"
                f"## Example\n[ON SCREEN: \"Example\"]\n{' '.join(['word'] * example_words)}.\n"
                "## Takeaway\n[ON SCREEN: \"Try\"]\nTry it once today.\n"
                "## CTA\n[ON SCREEN: \"ziro.digital\"]\nExplore AI learning at ziro.digital.\n")

    assert not [p for p in shape_problems(script(52), brief) if p.startswith("runtime")]
    too_long = [p for p in shape_problems(script(120), brief) if p.startswith("runtime")]
    assert too_long and "cut about" in too_long[0] and "26-34s" in too_long[0]
