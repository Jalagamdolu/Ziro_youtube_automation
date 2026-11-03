"""Research agent (D-03, D-10): the model picks searches and pages; code keeps a claim only if its
quote is on the fetched page, and fetches only URLs that search returned."""

from datetime import datetime
from typing import Any

from app.adapters import research
from app.adapters.search import Page, Result
from app.core.contracts import Brief

BRIEF = Brief(topic="What is retrieval-augmented generation?", audience="Indian students",
              learning_outcome="Explain RAG.", language="en", format="short", target_seconds=60,
              cta="Explore AI learning at ziro.digital")
URL = "https://example.org/rag"
QUOTE = "Retrieval-augmented generation lets a model look up documents before it answers."


class ScriptedChat:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies, self.prompts = replies, []
        self.calls: list[tuple[str, float]] = []

    def json(self, system: str, prompt: str) -> Any:
        self.prompts.append(prompt)
        self.calls += [("gemini-input", 100), ("gemini-output", 10)]
        return self.replies.pop(0)


class FakeWeb:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def search(self, query: str) -> list[Result]:
        return [Result(URL, "RAG explained")]

    def fetch(self, url: str) -> Page | None:
        self.fetched.append(url)
        text = f"Intro paragraph.\n{QUOTE.replace('look up', 'look  up')} More text follows."
        return Page(url, "RAG explained", text, datetime(2025, 3, 1))


def test_agent_keeps_only_quotes_found_on_the_fetched_page() -> None:
    chat = ScriptedChat([
        {"actions": [{"action": "search", "query": "what is RAG"}]},
        {"actions": [{"action": "fetch", "url": URL},
                     {"action": "fetch", "url": "https://not-searched.example/page"}]},
        {"actions": [
            {"action": "claim", "url": URL, "quote": QUOTE.replace("'", "’"),
             "claim": "RAG lets a model look up documents before answering."},
            {"action": "claim", "url": URL, "claim": "RAG makes answers correct.",
             "quote": "RAG makes every answer correct and cuts costs."},
            {"action": "done"}]},
    ])
    web = FakeWeb()
    topic = BRIEF.model_copy(update={"topic": "RAG for students"})  # not an explainer (D-40)
    claims = research.AgentResearch(chat, web, max_turns=5, target=3).find_claims(topic)

    assert web.fetched == [URL]  # the URL search never returned is refused
    assert "refused, not in your search results" in chat.prompts[2]
    verified = [c for c in claims if c.verification_status == "verified"]
    assert [(c.id, c.url, c.title) for c in verified] == [("C1", URL, "RAG explained")]
    assert verified[0].published_at == datetime(2025, 3, 1)
    assert [c.verification_status for c in claims] == ["verified", "unverified"]
    assert len(chat.prompts) == 3  # stopped at "done"


def test_agent_stops_at_max_turns_and_reports_usage() -> None:
    chat = ScriptedChat([{"actions": [{"action": "search", "query": "rag"}]}] * 2)
    agent = research.AgentResearch(chat, FakeWeb(), max_turns=2, target=3)
    assert agent.find_claims(BRIEF) == []
    assert agent.calls.count(("tavily-search", 1)) == 2
    assert agent.calls.count(("gemini-input", 100)) == 2


def test_short_quotes_are_not_evidence() -> None:
    page = Page(URL, "t", "RAG is useful.", None)
    claim = research.verify({"url": URL, "quote": "RAG is useful.", "claim": "RAG is useful."},
                            {URL: page}, "C1", {})
    assert claim.verification_status == "unverified"


def test_explainer_research_refuses_done_until_two_mechanism_claims() -> None:
    """D-40: "What is X?" needs how-it-works claims; "done" without them is refused."""
    claim = {"action": "claim", "url": URL, "quote": QUOTE, "claim": "RAG looks up documents."}
    chat = ScriptedChat([
        {"actions": [{"action": "search", "query": "how does RAG work"}]},
        {"actions": [{"action": "fetch", "url": URL}]},
        {"actions": [claim | {"kind": "definition"}, {"action": "done"}]},
        {"actions": [claim | {"kind": "mechanism"}, claim | {"kind": "mechanism"},
                     {"action": "done"}]},
    ])
    agent = research.AgentResearch(chat, FakeWeb(), max_turns=6, target=3)
    claims = agent.find_claims(BRIEF)
    assert "done refused: 0 of 2 mechanism claims" in chat.prompts[3]
    assert "how it works" in chat.prompts[0] or len(chat.prompts) == 4
    assert [c.kind for c in claims] == ["definition", "mechanism", "mechanism"]
    assert research.mechanism_count(claims) == 2


def test_an_unknown_kind_is_other() -> None:
    page = Page(URL, "t", QUOTE, None)
    claim = research.verify({"url": URL, "quote": QUOTE, "claim": "c", "kind": "benefit"},
                            {URL: page}, "C1", {})
    assert claim.kind == "other"
