"""Human-edit bridge (D-30): an edited package round-trips, and notes sit under failing lines."""

from app.adapters.llm import FixtureLLM
from app.adapters.research import FixtureResearch
from app.core.contracts import Brief
from app.nodes import human_edit

BRIEF = Brief(topic="What makes an AI agent different from a chatbot?", audience="a",
              learning_outcome="o", language="en", format="short", target_seconds=60,
              cta="Explore AI learning at ziro.digital")


def test_render_then_parse_returns_the_same_package_and_drops_notes() -> None:
    draft = FixtureLLM().write_package(BRIEF, FixtureResearch().find_claims(BRIEF), None)
    problem = f"packaging claims 'Boost' ({draft.titles[0][:60]!r}); no approved claim says it"
    text = human_edit.render(draft, [problem], "Dolender")

    lines = text.splitlines()
    at = lines.index(draft.titles[0])
    assert lines[at + 1].startswith("!! RULE: packaging claims 'Boost'")
    assert lines[at + 2].startswith("!! FIX: say what it does")
    parsed, editor = human_edit.parse(text)
    assert parsed == draft.model_copy(update={"script": draft.script.strip() + "\n"})
    assert editor == "Dolender"


def test_a_missing_section_is_named() -> None:
    try:
        human_edit.parse("=== EDITED BY ===\nDolender\n=== SCRIPT ===\n## Hook\n")
    except ValueError as error:
        assert "HOOKS" in str(error)
    else:
        raise AssertionError("expected ValueError")
