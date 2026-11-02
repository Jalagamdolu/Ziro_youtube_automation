"""Stock footage adapter (D-33): muted background clips behind the scene templates.

Pixabay is primary; Pexels is an optional secondary used only when PEXELS_API_KEY exists. No key at
all means no footage: scenes keep the solid brand background. Clips are filtered in code (no
AI-generated clips, nothing tagged as people or a brand), downloaded and stored, never hotlinked,
and cached by query hash, so a query is searched once (Pixabay asks for at least 24 h caching and
no bulk automated queries).
"""

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import httpx

from app.adapters import storage
from app.core import config
from app.core.errors import RetryableError
from app.core.log import log

PIXABAY = "https://pixabay.com/api/videos/"
PEXELS = "https://api.pexels.com/videos/search"
MAX_BYTES = 30_000_000  # skip very large files; backgrounds sit under a tint
FALLBACK_QUERY = "abstract technology background"
# Backgrounds may not be people-focused or show brands (brief: no endorsements, no fake products).
EXCLUDED = re.compile(
    r"\b(people|person|man|men|woman|women|girl|boy|child(ren)?|kid|face|portrait|crowd|"
    r"selfie|model|businessman|businesswoman|couple|family|logo|brand|trademark|apple|google|"
    r"microsoft|amazon|facebook|instagram|youtube|samsung|iphone|android|windows|macbook|nike)\b",
    re.IGNORECASE)
# Words of three letters or more that say nothing about what to show.
STOPWORDS = {"and", "are", "can", "does", "for", "from", "how", "into", "its", "that", "the",
             "their", "this", "was", "what", "when", "where", "which", "who", "why", "will",
             "with", "you", "your", "versus", "actually", "really", "make", "makes", "made",
             "different", "difference", "explained", "explain", "about", "all", "any", "learn",
             "first", "should", "would", "could", "one", "two", "new", "best", "way", "ways"}


@dataclass
class Clip:
    provider: str
    id: str
    page_url: str
    file_url: str
    seconds: float
    tags: str
    license: str
    license_url: str


class Stock(Protocol):
    name: str

    def search(self, query: str) -> list[Clip]:
        """Usable clips for a query, already filtered (AI-generated, people, brands)."""
        ...


class PixabayStock:
    name = "pixabay"

    def __init__(self, key: str) -> None:
        self.key = key

    def search(self, query: str) -> list[Clip]:
        data = _get(self.name, PIXABAY, params={
            "key": self.key, "q": query, "safesearch": "true", "per_page": 30,
            "min_width": 1280, "order": "popular"})
        clips = []
        for hit in data.get("hits", []):
            if hit.get("isAiGenerated") or EXCLUDED.search(hit.get("tags", "")):
                continue
            file = hit.get("videos", {}).get("medium", {})
            if file.get("url") and 0 < file.get("size", 0) <= MAX_BYTES:
                clips.append(Clip("pixabay", str(hit["id"]), hit["pageURL"], file["url"],
                                  float(hit.get("duration", 0)), hit.get("tags", ""),
                                  "Pixabay License", "https://pixabay.com/service/license-summary/"))
        return clips


class PexelsStock:
    name = "pexels"

    def __init__(self, key: str) -> None:
        self.key = key

    def search(self, query: str) -> list[Clip]:
        data = _get(self.name, PEXELS, params={"query": query, "per_page": 30},
                    headers={"authorization": self.key})
        clips = []
        for video in data.get("videos", []):
            slug = video.get("url", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            if EXCLUDED.search(slug):  # Pexels has no tags; its page slug describes the clip
                continue
            files = [f for f in video.get("video_files", []) if f.get("quality") == "hd"]
            if files:
                clips.append(Clip("pexels", str(video["id"]), video["url"], files[0]["link"],
                                  float(video.get("duration", 0)), slug, "Pexels License",
                                  "https://www.pexels.com/license/"))
        return clips


class MockStock:
    """No footage: every scene keeps the solid brand background (tests, no keys)."""

    name = "mock"

    def search(self, query: str) -> list[Clip]:
        return []


def background_query(topic: str) -> str:
    """Two content words from the topic (code, not a model), steered to abstract visuals."""
    words = list(dict.fromkeys(w for w in re.findall(r"[a-z]{3,}", topic.lower())
                               if w not in STOPWORDS))
    return " ".join(words[:2] + ["technology"]) if words else FALLBACK_QUERY


def find(stock: list[Stock], query: str, count: int) -> tuple[str, list[Clip], int]:
    """(query used, up to `count` clips, uncached searches made). Tries the topic query, then
    the fallback query, on each provider in order; cached results are reused by query hash."""
    searches = 0
    for q in dict.fromkeys([query, FALLBACK_QUERY]):
        for provider in stock:
            key = f"_stock/{hashlib.sha256(f'{provider.name}:{q}'.encode()).hexdigest()[:16]}"
            store = storage.get()
            if store.exists(f"{key}/results.json"):
                clips = [Clip(**c) for c in json.loads(store.read(f"{key}/results.json"))]
            else:
                clips = provider.search(q)
                searches += 1
                store.write(f"{key}/results.json",
                            json.dumps([asdict(c) for c in clips]).encode("utf-8"))
            if len(clips) >= count:
                return q, clips[:count], searches
    return query, [], searches


def download(clip: Clip) -> bytes:
    """The clip's file, from the cache or fetched once and stored (never hotlinked)."""
    key, store = f"_stock/files/{clip.provider}-{clip.id}.mp4", storage.get()
    if store.exists(key):
        return store.read(key)
    try:
        response = httpx.get(clip.file_url, timeout=120, follow_redirects=True)
    except httpx.TransportError as error:
        raise RetryableError(f"{clip.provider} download failed: {type(error).__name__}") from error
    if response.status_code != 200:
        raise RetryableError(f"{clip.provider} download returned {response.status_code}")
    store.write(key, response.content)
    return response.content


def _get(name: str, url: str, **kwargs: Any) -> Any:
    try:
        response = httpx.get(url, timeout=30, **kwargs)
    except httpx.TransportError as error:
        raise RetryableError(f"{name} unreachable: {type(error).__name__}") from error
    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableError(f"{name} returned {response.status_code}")
    if response.status_code >= 400:  # bad key: no footage this run, never a failed video
        log.warning("stock search refused", provider=name, status=response.status_code)
        return {}
    return response.json()


def get() -> list[Stock]:
    """Providers with a key, in config order. Empty list = solid backgrounds, no warning."""
    keys = {"pixabay": "PIXABAY_API_KEY", "pexels": "PEXELS_API_KEY"}
    built: dict[str, Any] = {"pixabay": PixabayStock, "pexels": PexelsStock}
    return [built[name](os.environ[keys[name]]) for name in config.load()["stock"]["providers"]
            if os.environ.get(keys[name])]
