"""A Short is at most 60 s (D-60), and source captures hide ads but never touch the quote (D-59)."""

from pathlib import Path

import pytest
from conftest import create, status
from pydantic import ValidationError

from app.adapters import prompts
from app.core.contracts import Brief
from app.nodes import script_checks


def brief(seconds: int) -> Brief:
    return Brief(topic="What is RAG?", audience="students", learning_outcome="Explain RAG.",
                 language="en", format="short", target_seconds=seconds,
                 cta="Explore AI learning at ziro.digital")


def script(example_words: int, sentences: int) -> str:
    per = example_words // sentences
    body = " ".join(" ".join(["word"] * (per - 1)) + " end." for _ in range(sentences))
    return (f"## Hook\n[ON SCREEN: \"Hi\"]\nWhat is RAG, really?\n## Relevance\n"
            f"[ON SCREEN: \"x\"]\nModels need facts.\n## Example\n[ON SCREEN: \"y\"]\n{body}\n"
            "## Takeaway\n"
            f"[ON SCREEN: \"z\"]\nTry it.\n## CTA\n[ON SCREEN: Ziro logo and \"ziro.digital\"]\n"
            "Explore AI learning at ziro.digital.")


def test_new_shorts_default_to_52_seconds(client) -> None:
    assert status(client, create(client))["brief"]["target_seconds"] == 52


def test_a_short_can_never_target_more_than_60_seconds() -> None:
    assert script_checks.runtime(brief(52)) == (44, 60)
    assert script_checks.runtime(brief(60)) == (51, 60)  # the +15% stops at 60
    with pytest.raises(ValidationError, match="15-60s"):
        brief(61)


def test_pauses_count_toward_the_60_seconds() -> None:
    fits = script(115, 10)  # ~125 spoken words
    assert not any("at most 60s" in p for p in script_checks.shape_problems(fits, brief(52)))
    long = script(126, 18)  # ~142 words: 57 s of speech, but its pauses push it past 60
    assert script_checks.video_seconds(long) > 60
    problems = script_checks.shape_problems(long, brief(52))
    assert any("a Short is at most 60s: cut about" in p for p in problems)


def test_the_writer_aims_for_130_words_and_never_past_the_cap() -> None:
    _, prompt = prompts.package(brief(52), [], None)
    assert "aim for about 130." in prompt
    assert f"over {script_checks.SHORT_WORD_CAP} words are rejected" in prompt


def test_capture_hides_ads_but_never_the_quote_or_its_text() -> None:
    capture = (Path(prompts.__file__).resolve().parents[3] / "templates" / "remotion"
               / "capture.mjs").read_text(encoding="utf-8")
    assert "el.contains(best) || best.contains(el)" in capture  # the quote and its page stay
    assert "placement" in capture and "adsbygoogle" in capture
    for edit in ("textContent =", "innerHTML", "innerText =", ".remove()", "replaceWith"):
        assert edit not in capture  # hide only; nothing on the page is ever rewritten
