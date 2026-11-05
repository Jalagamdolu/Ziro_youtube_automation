"""Uncited-line detector (D-43, deterministic) and the Haiku support check (D-44, flags only).
No paid API: the support chat is a stub.
"""

import importlib
from datetime import UTC, datetime
from typing import Any

from conftest import approve, create, status

from app.adapters import llm
from app.core.contracts import Brief, Claim
from app.nodes import human_edit, script_checks

scripting = importlib.import_module("app.nodes.scripting")  # app.nodes re-exports the function

BRIEF = Brief(topic="What is RAG?", audience="students", learning_outcome="Explain RAG.",
              language="en", format="short", target_seconds=40, cta="Explore AI at ziro.digital")
CLAIMS = [Claim(id=f"C{i}", claim=f"claim {i}", url="https://example.com", title="T",
                quote=quote, accessed_at=datetime(2026, 11, 1, tzinfo=UTC),
                verification_status="verified")
          for i, quote in [(1, "RAG connects a model with external knowledge bases."),
                           (2, "Algorithms retrieve snippets relevant to the question.")]]


def script(example: str) -> str:
    return (f"## Hook\nWhat is RAG?\n## Relevance\nModels need facts. [C1]\n## Example\n"
            f"{example}\n## Takeaway\nTry it.\n## CTA\n{BRIEF.cta}")


def test_every_example_sentence_needs_a_marker() -> None:
    problems = script_checks.uncited_problems(script(
        "First, algorithms retrieve snippets. [C2]\n"
        "The combined prompt is sent to the language model.\n"
        "The model blends its own knowledge with the facts."), BRIEF)
    assert len(problems) == 2
    assert "'The combined prompt is sent to the language model.'" in problems[0]


def test_questions_illustrations_and_viewer_lines_are_exempt() -> None:
    assert script_checks.uncited_problems(script(
        "What happens next? For example, imagine a shop's FAQ page. Imagine asking it a "
        "question. You type a question. If you add a document, try asking about it. "
        "Try it on your notes. Let's see. It retrieves snippets. [C2]"), BRIEF) == []


def test_marker_after_the_full_stop_still_counts() -> None:
    assert script_checks.uncited_problems(script("It retrieves snippets. [C2] It adds them. "
                                                 "[C1]"), BRIEF) == []


def test_only_body_sections_are_checked() -> None:
    long = Brief(**(BRIEF.model_dump() | {"format": "long", "target_seconds": 240}))
    text = ("## Hook\nA plain hook line.\n## Context\nModels read prompts.\n## Build\n"
            "It retrieves snippets. [C2]\n## Recap\nThat is all.\n## CTA\nGo.")
    assert [p.split(":")[0] for p in script_checks.uncited_problems(text, long)] == \
        ["uncited line in Context"]


def test_the_edit_box_explains_the_fix() -> None:
    assert "label it" in human_edit._fix("uncited line in Example: 'x' states a fact")


class StubSupport:
    model = "claude-haiku-5-5"

    def __init__(self, reply: Any) -> None:
        self.reply, self.calls, self.prompts = reply, [("claude-haiku-5-5-input", 10)], []

    def json(self, system: str, prompt: str, schema: Any = None) -> Any:
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_support_check_flags_lines_that_say_more_than_their_quote(monkeypatch) -> None:
    stub = StubSupport({"verdicts": [
        {"sentence": "RAG links a model to knowledge so answers are up to date.",
         "claims": ["C1"], "supported": False, "says_more": "answers are up to date"}]})
    monkeypatch.setattr(llm, "support_chat", lambda project_id: stub)
    monkeypatch.setattr(scripting.costs, "record_usage", lambda *a: None)
    text = "## Relevance\nRAG links a model to knowledge so answers are up to date. [C1]\n"
    report = scripting.support_flags("p1", text, CLAIMS)
    assert report["status"] == "ok" and report["verdicts"][0]["says_more"]
    assert "[C1] quote: RAG connects a model with external knowledge bases." in stub.prompts[0]


def test_support_check_never_blocks(monkeypatch) -> None:
    monkeypatch.setattr(llm, "support_chat", lambda project_id: StubSupport(RuntimeError("down")))
    monkeypatch.setattr(scripting.costs, "record_usage", lambda *a: None)
    report = scripting.support_flags("p1", "## Example\nIt retrieves. [C2]\n", CLAIMS)
    assert report == {"status": "not run", "reason": "down", "verdicts": []}


def test_support_check_does_not_run_in_prototype_mode() -> None:
    assert llm.support_chat("p1") is None


def test_script_review_shows_the_flags_and_approval_still_works(client, monkeypatch) -> None:
    stub = StubSupport({"verdicts": [
        {"sentence": "A chatbot answers.", "claims": ["C1"], "supported": True, "says_more": ""},
        {"sentence": "An agent always finishes the task.", "claims": ["C2"], "supported": False,
         "says_more": "'always finishes'"}]})
    monkeypatch.setattr(llm, "support_chat", lambda project_id: stub)
    project_id = create(client)
    approve(client, project_id)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "Support check" in page and "1 of 2 cited lines flagged." in page
    assert "An agent always finishes the task." in page
    approve(client, project_id)  # flags never block
    assert status(client, project_id)["status"] == "qa_review"


def test_prototype_script_review_says_the_check_was_not_run(client) -> None:
    project_id = create(client)
    approve(client, project_id)
    assert "Not run: needs production mode" in client.get(f"/ui/projects/{project_id}").text
