"""Stock photo adapter (D-33, D-34): one real photograph per scene that shows what it explains.

Pixabay is primary; Pexels is an optional secondary used only when PEXELS_API_KEY exists. No key at
all means no photos: scenes keep the solid brand background. Photos are filtered in code (no
AI-generated images, no identifiable faces or minors, no brands), downloaded and stored, never
hotlinked, and searches are cached by query hash (Pixabay asks for at least 24 h caching and no
bulk automated queries). The reviewer sees every photo, with alternatives, at qa_review.
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

PIXABAY = "https://pixabay.com/api/"
PEXELS = "https://api.pexels.com/v1/search"
CANDIDATES = 4  # photos offered per scene: the first is used, the rest are swaps at qa_review
# Not identifiable people (faces, portraits), no minors, no brands or product UIs (brief).
EXCLUDED = re.compile(
    r"\b(portrait|face|faces|headshot|selfie|smil(e|ing)|close-?up|beauty|model|eyes|"
    r"child(ren)?|kids?|baby|toddler|pupils?|boy|girl|teen(ager)?|"
    r"logo|brand|trademark|apple|macbook|iphone|ipad|google|microsoft|windows|amazon|facebook|"
    r"instagram|youtube|samsung|android|chatgpt|openai|nike|"
    # Hardware, industrial and consumer brands that show up in tech stock photos. A list can
    # never be complete; the reviewer's look at qa_review is the real gate (D-34).
    r"kawasaki|kuka|fanuc|abb|yaskawa|siemens|bosch|tesla|dell|lenovo|hp|asus|acer|intel|amd|"
    r"nvidia|sony|lg|huawei|xiaomi|oneplus|cisco|ibm|oracle|adidas|coca-?cola|pepsi|starbucks|"
    r"mcdonalds|toyota|bmw|mercedes|audi|ford|honda|lego|mindstorms?)\b", re.IGNORECASE)
STOPWORDS = {"and", "are", "can", "does", "for", "from", "how", "into", "its", "that", "the",
             "their", "this", "was", "what", "when", "where", "which", "who", "why", "will",
             "with", "you", "your", "versus", "actually", "really", "make", "makes", "made",
             "different", "difference", "explained", "explain", "about", "all", "any", "learn",
             "first", "should", "would", "could", "one", "two", "new", "best", "way", "ways",
             "card", "source", "side", "screen", "between", "them", "then", "only", "single"}


@dataclass
class Photo:
    provider: str
    id: str
    page_url: str
    file_url: str
    preview_url: str  # shown to the reviewer while choosing (temporary display is allowed)
    tags: str
    license: str
    license_url: str


class Stock(Protocol):
    name: str

    def search(self, query: str) -> list[Photo]:
        """Usable photos for a query, already filtered."""
        ...


class PixabayStock:
    name = "pixabay"

    def __init__(self, key: str) -> None:
        self.key = key

    def search(self, query: str) -> list[Photo]:
        data = _get(self.name, PIXABAY, params={
            "key": self.key, "q": query, "image_type": "photo", "orientation": "vertical",
            "safesearch": "true", "per_page": 30, "min_width": 700, "order": "popular"})
        return [Photo("pixabay", str(h["id"]), h["pageURL"], h["largeImageURL"], h["webformatURL"],
                      h.get("tags", ""), "Pixabay License",
                      "https://pixabay.com/service/license-summary/")
                for h in data.get("hits", [])
                if not h.get("isAiGenerated") and not EXCLUDED.search(h.get("tags", ""))]


class PexelsStock:
    name = "pexels"

    def __init__(self, key: str) -> None:
        self.key = key

    def search(self, query: str) -> list[Photo]:
        data = _get(self.name, PEXELS, params={"query": query, "orientation": "portrait",
                                               "per_page": 30},
                    headers={"authorization": self.key})
        return [Photo("pexels", str(p["id"]), p["url"], p["src"]["portrait"], p["src"]["medium"],
                      p.get("alt", ""), "Pexels License", "https://www.pexels.com/license/")
                for p in data.get("photos", []) if not EXCLUDED.search(p.get("alt", ""))]


def keywords(text: str, limit: int = 3) -> str:
    """A photo query from words in code (prototype mode, or when the model gives none)."""
    words = [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOPWORDS]
    return " ".join(list(dict.fromkeys(words))[:limit])


def candidates(stock: list[Stock], query: str) -> tuple[list[Photo], int]:
    """(up to CANDIDATES photos, uncached searches made) for one query, first provider that has
    any; results are cached by query hash so a query is searched once."""
    searches = 0
    for provider in stock:
        key = f"_stock/{hashlib.sha256(f'{provider.name}:photo:{query}'.encode()).hexdigest()[:16]}"
        store = storage.get()
        if store.exists(f"{key}/results.json"):
            photos = [Photo(**p) for p in json.loads(store.read(f"{key}/results.json"))
                      if not EXCLUDED.search(p["tags"])]  # filters may have grown since
        else:
            photos = provider.search(query)
            searches += 1
            store.write(f"{key}/results.json",
                        json.dumps([asdict(p) for p in photos]).encode("utf-8"))
        if photos:
            return photos[:CANDIDATES], searches
    return [], searches


def download(photo: Photo) -> bytes:
    """The photo, from the cache or fetched once and stored (never hotlinked)."""
    key, store = f"_stock/files/{photo.provider}-{photo.id}.jpg", storage.get()
    if store.exists(key):
        return store.read(key)
    try:
        response = httpx.get(photo.file_url, timeout=60, follow_redirects=True)
    except httpx.TransportError as error:
        raise RetryableError(f"{photo.provider} download failed: {type(error).__name__}") from error
    if response.status_code != 200:
        raise RetryableError(f"{photo.provider} download returned {response.status_code}")
    store.write(key, response.content)
    return response.content


def _get(name: str, url: str, **kwargs: Any) -> Any:
    try:
        response = httpx.get(url, timeout=30, **kwargs)
    except httpx.TransportError as error:
        raise RetryableError(f"{name} unreachable: {type(error).__name__}") from error
    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableError(f"{name} returned {response.status_code}")
    if response.status_code >= 400:  # bad key: no photos this run, never a failed video
        log.warning("stock search refused", provider=name, status=response.status_code)
        return {}
    return response.json()


def get() -> list[Stock]:
    """Providers with a key, in config order. Empty list = solid backgrounds, no warning."""
    keys = {"pixabay": "PIXABAY_API_KEY", "pexels": "PEXELS_API_KEY"}
    built: dict[str, Any] = {"pixabay": PixabayStock, "pexels": PexelsStock}
    return [built[name](os.environ[keys[name]]) for name in config.load()["stock"]["providers"]
            if os.environ.get(keys[name])]
