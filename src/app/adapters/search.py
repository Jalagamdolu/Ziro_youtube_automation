"""Search + fetch adapter (§2). Search finds candidate URLs (Tavily free tier, D-27); fetch reads
the publisher's own page with httpx + trafilatura, so every quote is verified against the source,
never against a search provider's summary.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx

from app.core.errors import FatalError, RetryableError

TAVILY = "https://api.tavily.com/search"
USER_AGENT = "ZiroResearchBot/0.1 (sandbox evaluation; fact-checking for educational videos)"


@dataclass
class Result:
    url: str
    title: str


@dataclass
class Page:
    url: str
    title: str
    text: str
    published_at: datetime | None


class Search(Protocol):
    def search(self, query: str) -> list[Result]: ...

    def fetch(self, url: str) -> Page | None:
        """The page's main text, or None when it cannot be read (paywall, PDF, 404)."""
        ...


class TavilySearch:
    def __init__(self, key: str) -> None:
        self.key = key

    def search(self, query: str) -> list[Result]:
        try:
            response = httpx.post(
                TAVILY, timeout=60, headers={"authorization": f"Bearer {self.key}"},
                json={"query": query, "max_results": 6, "search_depth": "basic"})
        except httpx.TransportError as error:
            raise RetryableError(f"tavily unreachable: {type(error).__name__}") from error
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableError(f"tavily returned {response.status_code}")
        if response.status_code >= 400:  # 432/433: plan credits used up; 401: bad key
            raise FatalError(f"tavily returned {response.status_code}: {response.text[:200]}")
        return [Result(r["url"], r.get("title", "")) for r in response.json().get("results", [])]

    def fetch(self, url: str) -> Page | None:
        return fetch(url)


def fetch(url: str) -> Page | None:
    import trafilatura

    try:
        response = httpx.get(url, timeout=30, follow_redirects=True,
                             headers={"user-agent": USER_AGENT})
    except httpx.TransportError:
        return None
    if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
        return None
    doc: Any = trafilatura.bare_extraction(response.text, url=url, with_metadata=True)
    if doc is None or not doc.text:
        return None
    return Page(url=str(response.url), title=doc.title or "", text=doc.text,
                published_at=_date(doc.date))


def _date(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def get() -> Search:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise FatalError("production research needs TAVILY_API_KEY (see .env.example)")
    return TavilySearch(key)
