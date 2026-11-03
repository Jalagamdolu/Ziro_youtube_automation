"""D-40: explainers ("What is X?") are built on how-it-works claims, end to end: research fails
loudly without them, the gate labels them, the prompt asks for them and the check enforces them."""

from datetime import UTC, datetime

import pytest

from app.adapters import prompts
from app.core.contracts import Brief, Claim
from app.core.errors import FatalError
from app.nodes import script_checks

NOW = datetime(2026, 11, 3, tzinfo=UTC)


def claim(cid: str, kind: str) -> Claim:
    return Claim(id=cid, claim=f"{cid} says something.", url="https://example.org", title="Doc",
                 quote="A quote that is long enough to count as evidence here.",
                 accessed_at=NOW, verification_status="verified", kind=kind)  # type: ignore[arg-type]


CLAIMS = [claim("C1", "definition"), claim("C2", "mechanism"), claim("C3", "mechanism")]


def brief(topic: str) -> Brief:
    return Brief(topic=topic, audience="students", learning_outcome="Explain it.", language="en",
                 format="short", target_seconds=60, cta="Explore AI learning at ziro.digital")


@pytest.mark.parametrize(("topic", "explainer"), [
    ("What is RAG?", True), ("what are embeddings", True), ("How does RAG work?", True),
    ("Explain vector databases", True), ("What makes an AI agent different from a chatbot?", False),
    ("Three practical GenAI portfolio projects for freshers", False)])
def test_explainer_topics(topic: str, explainer: bool) -> None:
    assert script_checks.is_explainer(topic) is explainer


def script(example: str) -> str:
    return f"## Hook\nWhat is RAG?\n\n## Example\n{example}\n\n## Takeaway\nTry it.\n"


def test_example_must_cite_two_mechanism_claims() -> None:
    vague = script("RAG connects a model to knowledge bases. [C1]\nIt looks things up. [C2]")
    assert "at least 2 mechanism claims (C2, C3); it cites 1" in \
        script_checks.mechanism_problems(vague, CLAIMS, "What is RAG?")[0]
    good = script("First it searches your documents. [C2]\nThen it adds them to the prompt. [C3]")
    assert script_checks.mechanism_problems(good, CLAIMS, "What is RAG?") == []
    assert script_checks.mechanism_problems(vague, CLAIMS, "RAG for students") == []


def test_prompt_keeps_explainers_on_topic_and_labels_claim_kinds() -> None:
    _, prompt = prompts.package(brief("What is RAG?"), CLAIMS, None)
    assert "No career,\n      portfolio, job or project lines" in prompt
    assert "citing the mechanism\n      claims (C2, C3)" in prompt
    assert "[C2] (mechanism) C2 says something." in prompt
    _, other = prompts.package(brief("Three practical GenAI portfolio projects"), CLAIMS, None)
    assert "This is an explainer" not in other and "{explainer}" not in other


def test_photo_prompt_is_literal_only() -> None:
    scenes = [{"on_screen": '"RAG"', "text": "RAG retrieves documents."}]
    _, prompt = prompts.photo_queries(brief("What is RAG?"), scenes)
    assert "photos for the literal, diagrams for the abstract" in prompt


def test_research_fails_loudly_without_mechanism_claims(monkeypatch) -> None:
    import importlib

    from app.adapters import research

    node = importlib.import_module("app.nodes.researching")  # app.nodes re-exports the function

    class Vague:
        calls: list = []

        def find_claims(self, _brief: Brief) -> list[Claim]:
            return [claim("C1", "definition"), claim("C2", "other"), claim("C3", "mechanism")]

    class Ctx:
        project_id = "p"

        def read_json(self, *_args: str) -> dict:
            return brief("What is RAG?").model_dump()

    monkeypatch.setattr(research, "get", lambda: Vague())
    monkeypatch.setattr(node.costs, "record_usage", lambda *a: None)
    with pytest.raises(FatalError, match=r"found 1 'how it works' \(mechanism\) claims; an "
                                         r"explainer needs 2.*C2 other: C2 says something"):
        node.researching(Ctx())  # type: ignore[arg-type]


def test_research_gate_labels_definition_and_mechanism(client, monkeypatch) -> None:
    from conftest import create

    from app.adapters import research

    class Labelled:
        calls: list = []

        def find_claims(self, _brief: Brief) -> list[Claim]:
            return CLAIMS

    monkeypatch.setattr(research, "get", lambda: Labelled())
    project_id = create(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "1 definition</strong>" in page and "2 mechanism</strong>" in page
    assert '<span class="pill ok">mechanism</span>' in page
