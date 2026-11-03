"""Research adapter. Prototype mode returns a fixture claim ledger whose URLs and quotes were
checked by hand against the live pages (D-19). Production mode runs the one agent (D-03): the
model chooses searches and pages; code fetches them and keeps a claim only if its quote appears
verbatim in the fetched page (D-10).
"""

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from app.adapters import llm, search
from app.adapters.llm import Chat, Usage
from app.core import config
from app.core.contracts import Brief, Claim
from app.nodes import script_checks

PAGE_CHARS = 6000  # page text shown to the model per fetch
MIN_QUOTE_WORDS = 8

SYSTEM = """You research facts for a short educational YouTube video by Ziro for Indian students,
early-career developers and career switchers. You build a claim ledger: every fact the script may
state, each backed by a sentence copied word for word from a web page you fetched.

Reply with JSON only: {"actions": [ ... ]}, up to 4 actions per turn, from:
  {"action": "search", "query": "..."}
  {"action": "fetch", "url": "..."}              (only URLs listed in your search results)
  {"action": "claim", "url": "...", "quote": "...", "claim": "...",
   "kind": "definition" | "mechanism" | "other"}
  {"action": "done"}
- quote: one or two complete sentences copied exactly from the fetched page text (at least 8
  words). Any change, even punctuation inside words, and the claim is discarded.
- claim: one plain sentence saying what the quote says, no stronger, no added facts.
- kind: "definition" says what the thing is; "mechanism" says how it works: one concrete step,
  component or flow (e.g. "documents are split into chunks and stored as embeddings in a vector
  database"); "other" for anything else. Benefits and marketing lines are never "mechanism".
- Prefer primary, authoritative sources: official documentation, the organisation's own pages,
  standards bodies, universities, established publications. Avoid forums, SEO listicles and
  anonymous blogs.
- Never collect salaries, placement or hiring figures, earnings, testimonials, partnerships,
  certifications, user or view counts: the video may not state them.
- Aim for {target} claims from at least 2 different sites that together cover the topic (what it
  is, how it works, one concrete example). Say "done" when you have them.{mechanism}"""
MECHANISM = """
- This video explains how something works, so at least {n} of your claims must be "mechanism"
  claims, taken from technical documentation (official docs, engineering guides, papers). Search
  for the steps ("how does X work step by step", "X architecture", "X pipeline"), not overviews.
  "done" is refused until you have them."""


class Research(Protocol):
    calls: list[Usage]

    def find_claims(self, brief: Brief) -> list[Claim]: ...


class FixtureResearch:
    calls: list[Usage] = []

    def find_claims(self, brief: Brief) -> list[Claim]:
        raw = json.loads((llm.fixture_dir(brief.topic) / "claims.json").read_text(encoding="utf-8"))
        return [Claim.model_validate(c) for c in raw]


class AgentResearch:
    def __init__(self, chat: Chat, web: search.Search, max_turns: int, target: int) -> None:
        self.chat, self.web, self.max_turns, self.target = chat, web, max_turns, target
        self.calls: list[Usage] = []

    def find_claims(self, brief: Brief) -> list[Claim]:
        found: dict[str, str] = {}  # url -> title, from search results
        pages: dict[str, search.Page] = {}
        claims: list[Claim] = []
        transcript = [f"Video topic: {brief.topic}\nAudience: {brief.audience}\n"
                      f"Learning outcome: {brief.learning_outcome}\nStart by searching."]
        explainer = script_checks.is_explainer(brief.topic)
        need = script_checks.MIN_MECHANISM if explainer else 0
        system = SYSTEM.replace("{target}", str(self.target)).replace(
            "{mechanism}", MECHANISM.replace("{n}", str(need)) if explainer else "")
        try:
            for turn in range(self.max_turns):
                reply = self.chat.json(system, "\n\n".join(transcript))
                actions = reply.get("actions", []) if isinstance(reply, dict) else []
                transcript.append("You: " + json.dumps(actions, ensure_ascii=False))
                results = [self._act(a, found, pages, claims) for a in actions[:4]]
                mechanism = mechanism_count(claims)
                if any(isinstance(a, dict) and a.get("action") == "done" for a in actions):
                    if mechanism >= need:
                        break
                    results.append(f"done refused: {mechanism} of {need} mechanism claims; find "
                                   "how it works in technical documentation")
                verified = sum(c.verification_status == "verified" for c in claims)
                transcript.append("Results:\n" + "\n\n".join(results)
                                  + f"\n\nClaims verified so far: {verified} "
                                  + f"({mechanism} mechanism)"
                                  + f"\nTurns left: {self.max_turns - turn - 1}")
                transcript = _trim(transcript)
        finally:
            self.calls += self.chat.calls
        return claims

    def _act(self, action: Any, found: dict[str, str], pages: dict[str, search.Page],
             claims: list[Claim]) -> str:
        kind = action.get("action") if isinstance(action, dict) else None
        if kind == "search":
            results = self.web.search(str(action.get("query", "")))
            self.calls.append(("tavily-search", 1))
            found |= {r.url: r.title for r in results}
            return f"search {action.get('query')!r}:\n" + "\n".join(
                f"- {r.title} — {r.url}" for r in results)
        if kind == "fetch":
            url = str(action.get("url", ""))
            if url not in found:
                return f"fetch {url}: refused, not in your search results"
            page = self.web.fetch(url)
            if page is None:
                return f"fetch {url}: could not read this page; pick another result"
            pages[url] = page
            return f"fetch {url} — {page.title}\n<<<PAGE\n{page.text[:PAGE_CHARS]}\nPAGE>>>"
        if kind == "claim":
            claim = verify(action, pages, f"C{len(claims) + 1}", found)
            claims.append(claim)
            if claim.verification_status == "verified":
                return f"claim {claim.id}: verified"
            return f"claim discarded: quote not found word for word in {action.get('url')}"
        if kind == "done":
            return "done"
        return f"unknown action {action!r}"


def verify(action: dict[str, Any], pages: dict[str, search.Page], claim_id: str,
           titles: dict[str, str]) -> Claim:
    """Deterministic quote check: the quote must appear in the fetched page text (D-10)."""
    url, quote = str(action.get("url", "")), str(action.get("quote", "")).strip()
    page = pages.get(url)
    ok = (page is not None and len(quote.split()) >= MIN_QUOTE_WORDS
          and _norm(quote) in _norm(page.text))
    raw = action.get("kind")
    kind: Literal["definition", "mechanism", "other"] = (
        "definition" if raw == "definition" else "mechanism" if raw == "mechanism" else "other")
    return Claim(id=claim_id, claim=str(action.get("claim", "")).strip(), url=url,
                 kind=kind,
                 title=(page.title if page and page.title else titles.get(url, url)),
                 quote=quote, accessed_at=datetime.now(UTC),
                 published_at=page.published_at if page else None,
                 verification_status="verified" if ok else "unverified")


def mechanism_count(claims: list[Claim]) -> int:
    return sum(c.kind == "mechanism" and c.verification_status == "verified" for c in claims)


def _norm(text: str) -> str:
    """Compare text, not typography: curly quotes, dashes, case and whitespace are unified."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans("‘’‚‛“”„‟–—‐‑", "''''\"\"\"\"----"))
    return re.sub(r"\s+", " ", text).strip().lower()


def _trim(transcript: list[str]) -> list[str]:
    """Keep only the latest page text in full; older pages shrink to their header line."""
    last = max((i for i, t in enumerate(transcript) if "<<<PAGE" in t), default=-1)
    return [t if i == last else re.sub(r"<<<PAGE.*?PAGE>>>", "[page text shown earlier]", t,
                                        flags=re.DOTALL)
            for i, t in enumerate(transcript)]


def get() -> Research:
    cfg = config.load()
    if cfg["mode"] == "prototype":
        return FixtureResearch()
    return AgentResearch(llm.chat(), search.get(), cfg["research"]["max_turns"],
                         cfg["research"]["target_claims"])
