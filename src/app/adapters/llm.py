"""LLM adapter. Prototype mode serves hand-written fixtures (D-19). Production mode, evaluation
phase (D-27): Gemini free tier, Groq free tier as fallback. Claude (D-02) stays the documented
paid upgrade.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core import config
from app.core.contracts import Brief, Claim, PackageDraft
from app.core.errors import FatalError, RetryableError
from app.core.log import log

FIXTURES = Path(__file__).parent / "fixtures"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
GROQ = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT = 180.0
MINUTE_RETRIES = 3  # per-minute 429s are waited out in place before the stage retry takes over
MAX_OUTPUT_TOKENS = 4000

# Usage of one paid call, as (price key in config.yaml, units). Free tier still records tokens.
Usage = tuple[str, float]


class QuotaExhausted(FatalError):
    """A provider's daily free-tier quota is used up; waiting minutes will not help."""


class Chat(Protocol):
    calls: list[Usage]

    def json(self, system: str, prompt: str) -> Any:
        """One completion, parsed as JSON."""
        ...


class LLM(Protocol):
    calls: list[Usage]

    def learning_outcome(self, brief: Brief) -> str:
        """One sentence: what the viewer can do after watching."""
        ...

    def write_package(self, brief: Brief, claims: list[Claim], notes: str | None) -> PackageDraft:
        """Script, hooks, titles and SEO for a brief, using only `claims`; `notes` asks for a
        revision (reviewer notes or failed checks)."""
        ...


class FixtureLLM:
    calls: list[Usage] = []

    def learning_outcome(self, brief: Brief) -> str:
        return brief.learning_outcome

    def write_package(self, brief: Brief, claims: list[Claim], notes: str | None) -> PackageDraft:
        folder = fixture_dir(brief.topic)
        package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
        package["script"] = (folder / "script.md").read_text(encoding="utf-8")
        # The CTA comes from the brief, as a real model would write it (T01).
        filled = json.loads(json.dumps(package).replace("{cta}", brief.cta))
        return PackageDraft.model_validate(filled)


class ModelLLM:
    """The LLM workflow steps (D-03): prompts in app.adapters.prompts (imported in the methods:
    prompts reads app.nodes, which imports this module), JSON out."""

    def __init__(self, chat: Chat) -> None:
        self.chat = chat
        self.calls = chat.calls

    def learning_outcome(self, brief: Brief) -> str:
        from app.adapters import prompts

        reply = self.chat.json(*prompts.learning_outcome(brief))
        return str(reply["learning_outcome"]).strip()

    def write_package(self, brief: Brief, claims: list[Claim], notes: str | None) -> PackageDraft:
        from app.adapters import prompts

        reply = self.chat.json(*prompts.package(brief, claims, notes))
        try:
            return PackageDraft.model_validate(reply)
        except ValueError as error:
            raise RetryableError(f"model returned an invalid package: {error}") from error


class GeminiChat:
    name = "gemini"

    def __init__(self, model: str, key: str, wait_max: float) -> None:
        self.model, self.key, self.wait_max = model, key, wait_max
        self.calls: list[Usage] = []

    def json(self, system: str, prompt: str) -> Any:
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
        data = _post(self, GEMINI.format(self.model), {"x-goog-api-key": self.key}, body)
        usage = data.get("usageMetadata", {})
        self.calls += [("gemini-input", usage.get("promptTokenCount", 0)),
                       ("gemini-output", usage.get("candidatesTokenCount", 0)
                        + usage.get("thoughtsTokenCount", 0))]
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as error:
            raise RetryableError(f"gemini returned no content: {str(data)[:300]}") from error
        return _parse(text)


class GroqChat:
    name = "groq"

    def __init__(self, model: str, key: str, wait_max: float) -> None:
        self.model, self.key, self.wait_max = model, key, wait_max
        self.calls: list[Usage] = []

    def json(self, system: str, prompt: str) -> Any:
        # gpt-oss spends hidden reasoning tokens before the JSON; keep reasoning low and the
        # output cap inside the free tier's 8,000 tokens/minute (D-28).
        body = {"model": self.model, "temperature": 0.7, "reasoning_effort": "low",
                "max_completion_tokens": MAX_OUTPUT_TOKENS,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}]}
        for _ in range(2):  # Groq's own JSON validation can reject one generation; try again
            try:
                data = _post(self, GROQ, {"authorization": f"Bearer {self.key}"}, body)
                break
            except FatalError as error:
                if "json_validate_failed" not in str(error):
                    raise
                log.info("llm returned invalid JSON, asking again", provider=self.name)
        else:
            raise RetryableError("groq could not produce valid JSON twice")
        usage = data.get("usage", {})
        self.calls += [("groq-input", usage.get("prompt_tokens", 0)),
                       ("groq-output", usage.get("completion_tokens", 0))]
        return _parse(data["choices"][0]["message"]["content"])


class FallbackChat:
    """Primary first; the fallback takes over for the rest of the stage once the primary's daily
    quota is gone or it keeps failing. Both out of daily quota fails the run cleanly."""

    def __init__(self, chats: list[GeminiChat | GroqChat]) -> None:
        self.chats = chats
        self.calls: list[Usage] = []

    def json(self, system: str, prompt: str) -> Any:
        reasons = []
        while self.chats:
            chat = self.chats[0]
            try:
                return chat.json(system, prompt)
            except (QuotaExhausted, RetryableError) as error:
                reasons.append(f"{chat.name}: {error}")
                if len(self.chats) == 1:
                    if all("daily" in r for r in reasons):
                        raise QuotaExhausted(
                            "free-tier daily quota exhausted on every LLM provider ("
                            + "; ".join(reasons) + "). Retry the run after the quota resets."
                        ) from error
                    raise
                log.warning("llm provider failed over", provider=chat.name, reason=str(error))
                self.chats = self.chats[1:]
            finally:
                self.calls += chat.calls
                chat.calls = []
        raise FatalError("no LLM provider configured")


def _post(chat: GeminiChat | GroqChat, url: str, headers: dict[str, str],
          body: dict[str, Any]) -> Any:
    for _ in range(MINUTE_RETRIES):
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
        except httpx.TransportError as error:  # timeouts included
            raise RetryableError(f"{chat.name} unreachable: {type(error).__name__}") from error
        if response.status_code == 429:
            daily, wait = _quota(response)
            if daily:
                raise QuotaExhausted(f"{chat.name} daily free-tier quota exhausted")
            if wait > chat.wait_max:
                raise RetryableError(f"{chat.name} rate limited for {wait:.0f}s")
            log.info("llm rate limited, waiting", provider=chat.name, seconds=wait)
            time.sleep(wait)
            continue
        if response.status_code >= 500:
            raise RetryableError(f"{chat.name} returned {response.status_code}")
        if response.status_code >= 400:  # bad key, bad model, bad request: retrying won't help
            raise FatalError(f"{chat.name} returned {response.status_code}: "
                             f"{response.text[:300]}")
        return response.json()
    raise RetryableError(f"{chat.name} still rate limited after {MINUTE_RETRIES} waits")


def _quota(response: httpx.Response) -> tuple[bool, float]:
    """(is the daily quota gone, seconds to wait) from a 429."""
    text = response.text
    daily = bool(re.search(r"PerDay|per day|\(RPD\)|\(TPD\)", text))
    wait = float(response.headers.get("retry-after", 0) or 0)
    delay = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', text)
    if delay:
        wait = float(delay.group(1))
    return daily, wait or 20.0


def _parse(text: str) -> Any:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RetryableError(f"model returned invalid JSON: {text[:200]!r}") from error


def fixture_dir(topic: str) -> Path:
    folder = FIXTURES / re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    if not folder.is_dir():
        known = ", ".join(sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()))
        raise FatalError(f"no fixture for this topic in prototype mode (have: {known})")
    return folder


def chat(stage: str = "default") -> FallbackChat:
    """Production chat for a stage: every provider with a key, in the stage's configured order
    (config.yaml llm.order; D-28)."""
    cfg = config.load()["llm"]
    wait = cfg["rate_limit_wait_max_seconds"]
    keys = {"gemini": os.environ.get("GEMINI_API_KEY"), "groq": os.environ.get("GROQ_API_KEY")}
    found: list[GeminiChat | GroqChat] = []
    for name in cfg["order"].get(stage, cfg["order"]["default"]):
        if key := keys[name]:
            found.append(GeminiChat(cfg["gemini_model"], key, wait) if name == "gemini"
                         else GroqChat(cfg["groq_model"], key, wait))
    if not found:
        raise FatalError("production mode needs GEMINI_API_KEY or GROQ_API_KEY (see .env.example)")
    return FallbackChat(found)


def get(stage: str = "default") -> LLM:
    if config.load()["mode"] == "prototype":
        return FixtureLLM()
    return ModelLLM(chat(stage))
