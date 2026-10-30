"""The content_package / brief / decision contracts reject what the brief forbids."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.contracts import Brief, Chapter, ContentPackage, Decision, Hook

BRIEF = Brief(topic="t", audience="a", learning_outcome="o", language="en", format="short",
              target_seconds=60, cta="c")


def _package(**overrides: object) -> ContentPackage:
    fields: dict[str, object] = {
        "brief": BRIEF, "claims": [], "script": "s",
        "hooks": [Hook(text=f"h{i}", score=1, explanation="e") for i in range(5)],
        "titles": [f"t{i}" for i in range(10)], "top_titles": ["t0", "t1", "t2"],
        "thumbnail_text": "Agents vs bots", "description": "d", "tags": ["x"],
        "target_queries": ["q1", "q2", "q3"], "chapters": [Chapter(start_seconds=0, title="i")],
    }
    return ContentPackage.model_validate(fields | overrides)


def test_valid_package_round_trips() -> None:
    package = _package()
    assert ContentPackage.model_validate_json(package.model_dump_json()) == package
    assert package.schema_version == "1.0"


@pytest.mark.parametrize("overrides", [
    {"hooks": [Hook(text="h", score=1, explanation="e")] * 4},
    {"titles": ["t"] * 9},
    {"thumbnail_text": "four words is too many"},
    {"tags": ["t"] * 16},
])
def test_package_rejects_out_of_contract(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _package(**overrides)


@pytest.mark.parametrize("fmt,seconds", [("short", 90), ("long", 120)])
def test_brief_duration_must_fit_format(fmt: str, seconds: int) -> None:
    with pytest.raises(ValidationError):
        Brief(**(BRIEF.model_dump() | {"format": fmt, "target_seconds": seconds}))


def test_decision_rules() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        Decision(decision_id="d", gate="script_review", decision="reject", reviewer="Hemu",
                 decided_at=now)
    with pytest.raises(ValidationError):
        Decision(decision_id="d", gate="qa_review", decision="approve", reviewer="Hemu",
                 decided_at=now)
