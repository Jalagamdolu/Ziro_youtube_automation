"""T03: every figure or date traces to an approved claim; invented and banned claims are blocked."""

import html
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.adapters.research import FixtureResearch
from app.core.contracts import Brief, Claim
from app.nodes.script_checks import claim_problems

CLAIMS = [Claim(id="C1", claim="c", url="https://example.org", title="t", quote="q",
                accessed_at=datetime.now(UTC), verification_status="verified")]


def _script(narration: str) -> str:
    return f"## Example\n[ON SCREEN: card]\n{narration}\n"


def test_sourced_figure_passes() -> None:
    assert claim_problems(_script("Agents finished 40% of tasks in that study. [C1]"), CLAIMS) == []


@pytest.mark.parametrize("narration", [
    "Agents finished 40% of tasks in that study.",           # figure with no source
    "This changed in March.",                                 # date with no source
    "Agents finished 40% of tasks in that study. [C7]",       # cites an unapproved claim
])
def test_unsourced_or_unapproved_claims_are_blocked(narration: str) -> None:
    assert claim_problems(_script(narration), CLAIMS)


@pytest.mark.parametrize("narration", [
    "Learners land a salary hike after this course.",
    "Our students got placed at top companies.",
    "Read this testimonial from a learner.",
    "Ziro is a certified partner of every big lab.",
    "Start earning from your first project.",
])
def test_banned_claim_language_is_blocked(narration: str) -> None:
    assert any("banned" in p for p in claim_problems(_script(narration), CLAIMS))


def test_learning_is_not_mistaken_for_earning() -> None:
    assert claim_problems(_script("Keep learning by building."), CLAIMS) == []


SNAPSHOTS = Path(__file__).resolve().parents[1] / "manual_qa" / "source-snapshots"


def _page_text(path: Path) -> str:
    raw = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", path.read_text(encoding="utf-8"))
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def test_fixture_quotes_appear_in_saved_snapshots() -> None:
    brief = Brief(topic="What makes an AI agent different from a chatbot?", audience="a",
                  learning_outcome="o", language="en", format="short", target_seconds=60, cta="c")
    for claim in FixtureResearch().find_claims(brief):
        name = re.sub(r"[^a-z0-9]+", "-", claim.url.removeprefix("https://")).strip("-")
        assert claim.quote in _page_text(SNAPSHOTS / f"{name}.html"), claim.id


def test_fixture_ledger_is_fully_sourced() -> None:
    brief = Brief(topic="What makes an AI agent different from a chatbot?", audience="a",
                  learning_outcome="o", language="en", format="short", target_seconds=60, cta="c")
    for claim in FixtureResearch().find_claims(brief):
        assert claim.url.startswith("https://") and claim.quote and claim.title
        assert claim.verification_status == "verified"
