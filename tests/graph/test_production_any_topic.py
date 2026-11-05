"""mode: production on a topic with no fixture (brief §01: a reviewer enters a different topic).
Real adapters, real checks; only the network is mocked (respx). Daily quota exhaustion on every
free tier fails the run cleanly at the first LLM stage, before anything is rendered (D-27).
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from conftest import create, status
from sqlalchemy import select

from app.adapters import llm, search
from app.core import config, db
from app.core.models import Cost

FIXTURE = Path(llm.__file__).parent / "fixtures" / "what-makes-an-ai-agent-different-from-a-chatbot"
TOPIC = "Chatbots versus AI agents for first-year students"  # no fixture for this topic
CTA = "Explore AI learning at ziro.digital"
GEMINI_URL = llm.GEMINI.format(config.load()["llm"]["gemini_model"])


@pytest.fixture
def production(pipeline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    config.load()["mode"] = "production"  # the pipeline fixture's config dict, this test only
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(name, "test-key")


def gemini(payload: object) -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
        "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200}})


def page(title: str, quote: str) -> httpx.Response:
    filler = "This page explains the topic for developers in plain language. " * 8
    html = f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1>" \
           f"<p>{filler}</p><p>{quote}</p><p>{filler}</p></article></body></html>"
    return httpx.Response(200, html=html)


@respx.mock
def test_any_topic_reaches_script_review_through_real_adapters(client, production) -> None:
    claims = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))
    package = json.loads((FIXTURE / "package.json").read_text(encoding="utf-8"))
    package["script"] = (FIXTURE / "script.md").read_text(encoding="utf-8")
    package = json.loads(json.dumps(package).replace("{cta}", CTA))
    respx.post(search.TAVILY).mock(return_value=httpx.Response(200, json={
        "results": [{"url": c["url"], "title": c["title"]} for c in claims]}))
    for c in claims:
        respx.get(c["url"]).mock(return_value=page(c["title"], c["quote"]))
    respx.post(GEMINI_URL).mock(side_effect=[
        gemini({"learning_outcome": "Tell a chatbot from an AI agent with one test."}),
        gemini({"actions": [{"action": "search", "query": "AI agent vs chatbot definition"}]}),
        gemini({"actions": [{"action": "fetch", "url": c["url"]} for c in claims]}),
        gemini({"actions": [{"action": "claim", "url": c["url"], "quote": c["quote"],
                             "claim": c["claim"]} for c in claims] + [{"action": "done"}]}),
    ])
    groq = respx.post(llm.GROQ).mock(return_value=httpx.Response(200, json={  # scripting (D-28)
        "choices": [{"message": {"content": json.dumps(package)}}],
        "usage": {"prompt_tokens": 1500, "completion_tokens": 300}}))

    project_id = create(client, prompt=TOPIC)
    run = status(client, project_id)
    assert run["status"] == "script_review", run["jobs"]  # claims + script, one gate (D-50)

    assert run["brief"]["topic"] == TOPIC  # T01: the entered topic survives unchanged
    with db.session() as s:
        rows = s.scalars(select(Cost).where(Cost.project_id == project_id)).all()
    tokens = {(r.stage, r.provider): r.units for r in rows if r.provider.endswith("-input")}
    tokens = {k: sum(r.units for r in rows if (r.stage, r.provider) == k) for k in tokens}
    assert tokens == {("draft", "gemini-input"): 1000, ("researching", "gemini-input"): 3000,
                      ("scripting", "groq-input"): 1500}  # scripting is Groq-first (D-28)
    assert groq.call_count == 1
    assert sum(r.units for r in rows if r.provider == "tavily-search") == 1
    assert run["total_cost_usd"] == 0.0  # free tier, counts kept for the paid estimate


@respx.mock
def test_daily_quota_on_every_provider_fails_before_research(client, production) -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(429, json={"error": {"details": [
        {"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}))
    respx.post(llm.GROQ).mock(return_value=httpx.Response(429, json={"error": {
        "message": "Rate limit reached on tokens per day (TPD)"}}))

    project_id = create(client, prompt=TOPIC)
    run = status(client, project_id)
    assert run["status"] == "failed"
    failed = [j for j in run["jobs"] if j["status"] == "failed"]
    assert [j["stage"] for j in failed] == ["draft"]  # fatal: not retried
    assert "daily quota exhausted on every LLM provider" in failed[0]["error_message"]
    assert not [a for a in run["artifacts"] if a["stage"] != "draft"]
