"""Optional live smoke test (D-27): one tiny call to each configured free tier. Never runs by
default; `make test-live` (ZIRO_LIVE=1, keys in .env) spends a few free-tier requests.
"""

import os

import pytest

from app.adapters import llm, search

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("ZIRO_LIVE") != "1", reason="set ZIRO_LIVE=1")]


def test_each_llm_provider_answers_json() -> None:
    for chat in llm.chat().chats:
        reply = chat.json("Reply with JSON only.", 'Return {"ok": true}.')
        assert reply == {"ok": True}, chat.name
        assert chat.calls and all(units > 0 for _, units in chat.calls), chat.name


def test_search_then_fetch_a_result() -> None:
    web = search.get()
    results = web.search("Python official tutorial")
    assert results
    pages = [web.fetch(r.url) for r in results[:3]]
    assert any(p and len(p.text) > 200 for p in pages)
