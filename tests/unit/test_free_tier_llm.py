"""Free-tier LLM adapters (D-27): rate limits wait or retry, daily quota fails over to Groq, both
exhausted fails cleanly, token counts are recorded. HTTP is mocked with respx; nothing is called.
"""

import json

import httpx
import pytest
import respx

from app.adapters import llm
from app.core.errors import FatalError, RetryableError

GEMINI_URL = llm.GEMINI.format("gemini-test")


def gemini_reply(payload: object) -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30}})


def groq_reply(payload: object) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "usage": {"prompt_tokens": 90, "completion_tokens": 20}})


def gemini_429(quota_id: str, delay: str = "2s") -> httpx.Response:
    return httpx.Response(429, json={"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": quota_id}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}})


GROQ_DAILY = httpx.Response(429, json={"error": {
    "message": "Rate limit reached for model on requests per day (RPD): Limit 1000, Used 1000"}})


def chats() -> llm.FallbackChat:
    return llm.FallbackChat([llm.GeminiChat("gemini-test", "g-key", 60),
                             llm.GroqChat("groq-test", "q-key", 60)])


@respx.mock
def test_gemini_answer_is_parsed_and_tokens_recorded() -> None:
    respx.post(GEMINI_URL).mock(return_value=gemini_reply({"learning_outcome": "Explain X."}))
    chat = chats()
    assert chat.json("system", "prompt") == {"learning_outcome": "Explain X."}
    assert chat.calls == [("gemini-input", 120), ("gemini-output", 30)]


@respx.mock
def test_per_minute_limit_is_waited_out(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    respx.post(GEMINI_URL).mock(side_effect=[
        gemini_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "7s"),
        gemini_reply({"ok": True})])
    assert chats().json("s", "p") == {"ok": True}
    assert waits == [7.0]


@respx.mock
def test_long_per_minute_wait_becomes_a_stage_retry_without_failover() -> None:
    respx.post(GEMINI_URL).mock(return_value=gemini_429(
        "GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "300s"))
    groq = respx.post(llm.GROQ).mock(return_value=groq_reply({"ok": True}))
    chat = llm.FallbackChat([llm.GeminiChat("gemini-test", "g-key", 60)])
    with pytest.raises(RetryableError, match="rate limited for 300s"):
        chat.json("s", "p")
    assert not groq.called


@respx.mock
def test_daily_quota_fails_over_to_groq() -> None:
    respx.post(GEMINI_URL).mock(return_value=gemini_429(
        "GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    respx.post(llm.GROQ).mock(return_value=groq_reply({"ok": True}))
    chat = chats()
    assert chat.json("s", "p") == {"ok": True}
    assert chat.calls == [("groq-input", 90), ("groq-output", 20)]
    assert chat.json("s", "p") == {"ok": True}  # Gemini is not retried within the stage
    assert respx.calls.call_count == 3


@respx.mock
def test_both_daily_quotas_gone_fails_cleanly() -> None:
    respx.post(GEMINI_URL).mock(return_value=gemini_429(
        "GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    respx.post(llm.GROQ).mock(return_value=GROQ_DAILY)
    with pytest.raises(llm.QuotaExhausted, match="Retry the run after the quota resets"):
        chats().json("s", "p")


@respx.mock
def test_server_errors_retry_and_bad_requests_do_not() -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(503))
    respx.post(llm.GROQ).mock(return_value=httpx.Response(401, json={"error": "invalid key"}))
    with pytest.raises(FatalError, match="groq returned 401"):  # after failing over from 503
        chats().json("s", "p")
    with pytest.raises(RetryableError):
        llm.FallbackChat([llm.GeminiChat("gemini-test", "g-key", 60)]).json("s", "p")


@respx.mock
def test_invalid_json_is_retryable() -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "Sure! Here it is: {"}]}}]}))
    with pytest.raises(RetryableError, match="invalid JSON"):
        llm.FallbackChat([llm.GeminiChat("gemini-test", "g-key", 60)]).json("s", "p")


def test_production_without_keys_fails_with_a_clear_message(monkeypatch: pytest.MonkeyPatch
                                                              ) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(FatalError, match="GEMINI_API_KEY or GROQ_API_KEY"):
        llm.chat()
