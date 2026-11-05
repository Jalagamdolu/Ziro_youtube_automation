"""Claude writer (D-42) and budget caps (D-45). The Anthropic SDK talks to a mock transport and
Groq to respx; nothing paid is ever called.
"""

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
import respx
from conftest import create

from app.adapters import llm, prompts
from app.core import config, costs, db
from app.core.contracts import Brief, PackageDraft
from app.core.errors import FatalError, RetryableError

BRIEF = Brief(topic="What is RAG?", audience="students", learning_outcome="Explain RAG.",
              language="en", format="short", target_seconds=45, cta="Explore AI at ziro.digital")
PACKAGE = {"script": "## Hook\nHi", "hooks": [{"text": f"h{i}", "explanation": "e"}
                                              for i in range(5)],
           "titles": [f"t{i}" for i in range(10)], "thumbnail_text": "x", "description": "d",
           "tags": ["a"], "target_queries": ["q1", "q2", "q3"],
           "chapters": [{"start_seconds": 0, "title": "Hook"}]}


def message(payload: object, stop: str = "end_turn") -> httpx2.Response:
    return httpx2.Response(200, json={
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 0}})


def claude(handler: Callable[[httpx2.Request], httpx2.Response]) -> llm.ClaudeChat:
    chat = llm.ClaudeChat("claude-opus-5-5", "k", "high", 16000, "p1")
    chat.client = anthropic.Anthropic(api_key="k", max_retries=0,
                                      http_client=anthropic.DefaultHttpxClient(
                                          transport=httpx2.MockTransport(handler)))
    return chat


@pytest.fixture(autouse=True)
def _no_db_budget(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> list[Any]:
    """Budget checks are recorded, not run against a database, except in the budget tests."""
    seen: list[Any] = []
    if "client" not in request.fixturenames:
        monkeypatch.setattr(costs, "check_budget", lambda *a: seen.append(a))
    return seen


def test_package_comes_back_validated_with_the_system_prompt_cached(
        _no_db_budget: list[Any]) -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return message(PACKAGE)

    writer = llm.ModelLLM(llm.FallbackChat([claude(handler)]))
    draft = writer.write_package(BRIEF, [], None)
    assert isinstance(draft, PackageDraft) and draft.titles[0] == "t0"
    body = sent[0]
    assert body["model"] == "claude-opus-5-5" and body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"  # structured output
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Banned and outcome words" in body["system"][0]["text"]  # fixed rules are cached
    assert "Banned and outcome words" not in body["messages"][0]["content"].split("# Hard")[0]
    assert writer.calls == [("claude-opus-5-5-input", 100), ("claude-opus-5-5-output", 50),
                            ("claude-opus-5-5-cache-write", 3000),
                            ("claude-opus-5-5-cache-read", 0)]
    assert _no_db_budget[0][0] == "p1"  # checked before the call, for this run


def test_system_prompt_is_identical_across_briefs_so_the_cache_hits() -> None:
    other = BRIEF.model_copy(update={"topic": "Git basics", "target_seconds": 60})
    assert prompts.package(BRIEF, [], None)[0] == prompts.package(other, [], "fix it")[0]


@respx.mock
def test_claude_down_falls_back_to_groq_for_the_rest_of_the_stage() -> None:
    respx.post(llm.GROQ).mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps({"ok": True})}}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 2}}))
    overloaded = claude(lambda r: httpx2.Response(529, json={"type": "error", "error": {
        "type": "overloaded_error", "message": "Overloaded"}}))
    chat = llm.FallbackChat([overloaded, llm.GroqChat("groq-test", "q-key", 60)])
    assert chat.json("s", "p") == {"ok": True}
    assert [c.name for c in chat.chats] == ["groq"]


def test_errors_map_to_retry_or_fail() -> None:
    with pytest.raises(RetryableError, match="RateLimitError"):
        claude(lambda r: httpx2.Response(429, json={"type": "error", "error": {
            "type": "rate_limit_error", "message": "slow down"}})).json("s", "p")
    with pytest.raises(FatalError, match="401"):
        claude(lambda r: httpx2.Response(401, json={"type": "error", "error": {
            "type": "authentication_error", "message": "invalid x-api-key"}})).json("s", "p")
    with pytest.raises(RetryableError, match="refusal"):
        claude(lambda r: message({}, stop="refusal")).json("s", "p")


def test_scripting_uses_claude_first_and_runs_without_a_key(monkeypatch: pytest.MonkeyPatch
                                                            ) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "q-key")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert [c.name for c in llm.chat("scripting").chats] == ["groq", "gemini"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    chats = llm.chat("scripting", "p1").chats
    assert [c.name for c in chats] == ["claude", "groq", "gemini"]
    assert isinstance(chats[0], llm.ClaudeChat) and chats[0].project_id == "p1"
    assert chats[0].model == config.load()["llm"]["claude_model"]  # configurable
    assert [c.name for c in llm.chat().chats] == ["claude", "gemini", "groq"]  # D-51


def _caps(tokens: int, usd: float) -> None:
    cfg = config.load()  # the pipeline fixture's dict, this test only
    cfg["budget"] = {"max_tokens_per_run": tokens, "max_usd_per_day": usd}
    cfg["prices"]["claude-opus-5-5-output"] = 20e-6


def test_per_run_token_cap_stops_the_call_before_it_is_made(client) -> None:
    project_id = create(client)
    _caps(tokens=50_000, usd=100.0)
    costs.record_usage(project_id, "scripting", [("claude-opus-5-5-output", 30_000)])
    costs.check_budget(project_id, 10_000, 0.2, [])  # 40k: fits
    with pytest.raises(costs.BudgetExceeded, match="per-run cap of 50,000"):
        costs.check_budget(project_id, 10_000, 0.2, [("claude-opus-5-5-output", 15_000)])


def test_daily_spend_cap_counts_every_run_today(client) -> None:
    first, second = create(client), create(client)
    _caps(tokens=10_000_000, usd=1.0)
    costs.record_usage(first, "scripting", [("claude-opus-5-5-output", 40_000)])  # $0.80
    costs.check_budget(second, 1_000, 0.15, [])
    with pytest.raises(costs.BudgetExceeded, match="daily cap of \\$1.00"):
        costs.check_budget(second, 1_000, 0.25, [])


def test_a_run_over_budget_fails_cleanly_with_the_reason(client, monkeypatch) -> None:
    from conftest import status

    from app.adapters import research

    config.load()["mode"] = "production"  # Claude writes, with a tiny token cap
    _caps(tokens=1_000, usd=100.0)
    monkeypatch.setattr(research, "get", lambda: research.FixtureResearch())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    called: list[Any] = []
    monkeypatch.setattr(anthropic.resources.messages.Messages, "parse",
                        lambda *a, **k: called.append(a))
    project_id = create(client, learning_outcome="Tell a chatbot from an agent.")
    run = status(client, project_id)
    assert run["status"] == "failed" and not called
    failed = [j for j in run["jobs"] if j["status"] == "failed"][-1]
    assert failed["stage"] == "scripting" and "per-run cap" in failed["error_message"]
    with db.session() as s:
        assert costs.total(s, project_id) == 0.0
