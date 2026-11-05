"""A Short's requested length is a ceiling (D-62; at most 60 s, D-60), and source captures hide
ads but never touch the quote (D-59)."""

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


def test_new_shorts_default_to_at_most_60_seconds(client) -> None:
    assert status(client, create(client))["brief"]["target_seconds"] == 60


def test_the_requested_length_is_a_ceiling() -> None:
    assert script_checks.runtime(brief(40)) == (34, 40)  # 15% under is fine, over never
    assert script_checks.runtime(brief(60)) == (51, 60)
    with pytest.raises(ValidationError, match="15-60s"):
        brief(61)


def test_a_40s_short_aims_at_90_percent_at_its_voices_rate(monkeypatch) -> None:
    # Kokoro speaks ~160 wpm (prototype, tests); Sarvam's Ishita ~130 (D-62)
    assert script_checks.word_budget(brief(40)) == (91, 96, 98)
    _, prompt = prompts.package(brief(40), [], None)
    assert "aim for about 96." in prompt and "over 98 words are rejected" in prompt
    assert "must not run longer than 40 s" in prompt and "(160 words per minute" in prompt
    monkeypatch.setattr(script_checks.engines, "voice", lambda: "sarvam")
    assert script_checks.word_budget(brief(40)) == (74, 78, 79)  # 78 words ~ 36 s of Ishita


def test_pauses_count_toward_the_requested_length() -> None:
    rate = script_checks.speech_rate(brief(40))
    fits = script(80, 8)  # ~96 spoken words: about 39 s with its pauses
    assert script_checks.video_seconds(fits, rate) <= 40
    assert not any("asked for at most" in p for p in script_checks.shape_problems(fits, brief(40)))
    over = script(84, 21)  # ~100 words: 37.5 s of speech, but 25 sentence pauses push it past 40
    assert script_checks.video_seconds(over, rate) > 40
    assert any("it was asked for at most 40s: cut about" in p
               for p in script_checks.shape_problems(over, brief(40)))


def test_capture_hides_ads_but_never_the_quote_or_its_text() -> None:
    capture = (Path(prompts.__file__).resolve().parents[3] / "templates" / "remotion"
               / "capture.mjs").read_text(encoding="utf-8")
    assert "el.contains(best) || best.contains(el)" in capture  # the quote and its page stay
    assert "placement" in capture and "adsbygoogle" in capture
    for edit in ("textContent =", "innerHTML", "innerText =", ".remove()", "replaceWith"):
        assert edit not in capture  # hide only; nothing on the page is ever rewritten
