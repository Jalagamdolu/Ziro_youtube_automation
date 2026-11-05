"""Sarvam TTS (D-46) through respx, and which engines run without keys. Nothing paid is called."""

import base64
import json

import httpx
import pytest
import respx

from app.adapters import llm, tts
from app.core import config, costs, engines
from app.core.errors import FatalError, RetryableError

WAV = b"RIFF....WAVEfmt fake"


def sarvam(project_id: str | None = "p1") -> tts.SarvamTTS:
    cfg = config.load()
    return tts.SarvamTTS(cfg["tts"]["sarvam"], cfg["pronunciation"], "k", project_id)


@pytest.fixture(autouse=True)
def _budget(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(costs, "check_budget", lambda *a: seen.append(a))
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    return seen


@respx.mock
def test_request_carries_the_voice_from_config_and_says_zyro(_budget: list) -> None:
    route = respx.post(tts.SARVAM).mock(return_value=httpx.Response(200, json={
        "request_id": "r1", "audios": [base64.b64encode(WAV).decode()]}))
    assert sarvam().wav("Explore AI learning at ziro.digital, says Ziro.") == WAV
    body = json.loads(route.calls[0].request.content)
    sent = config.load()["tts"]["sarvam"]
    assert (body["model"], body["speaker"], body["language_code"]) == (
        sent["model"], sent["speaker"], "en-IN")
    assert body["speech_sample_rate"] == tts.RATE
    assert body["text"] == "Explore AI learning at Zyro dot digital, says Zyro."  # spoken only
    assert route.calls[0].request.headers["api-subscription-key"] == "k"
    assert _budget and _budget[0][0] == "p1"  # checked before the call


@respx.mock
def test_rate_limits_and_server_errors_are_retried_then_succeed() -> None:
    ok = httpx.Response(200, json={"audios": [base64.b64encode(WAV).decode()]})
    route = respx.post(tts.SARVAM).mock(side_effect=[httpx.Response(429), httpx.Response(503),
                                                     ok])
    assert sarvam().wav("Hello.") == WAV
    assert route.call_count == 3


@respx.mock
def test_gives_up_after_its_attempts_and_bad_requests_fail_at_once() -> None:
    route = respx.post(tts.SARVAM).mock(return_value=httpx.Response(500))
    with pytest.raises(RetryableError):
        sarvam().wav("Hello.")
    assert route.call_count == config.load()["tts"]["sarvam"]["attempts"]
    respx.post(tts.SARVAM).mock(return_value=httpx.Response(403, json={"error": "bad key"}))
    with pytest.raises(FatalError, match="403"):
        sarvam().wav("Hello.")


def test_captions_keep_the_written_brand_name() -> None:
    assert "Ziro" in tts.spoken_text("Ziro", config.load()["pronunciation"])  # Kokoro, captions
    assert sarvam().said("Ziro") == "Zyro"


def test_no_keys_means_fallback_engines_and_banners(monkeypatch: pytest.MonkeyPatch) -> None:
    config.load()["mode"] = "production"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "q")
    found = engines.status()
    assert (found["writer"], found["voice"]) == ("groq/gemini", "kokoro")
    assert found["keys"]["ANTHROPIC_API_KEY"] is False  # names and presence only
    assert any("No ANTHROPIC_API_KEY" in b for b in engines.banners())
    assert any("No SARVAM_API_KEY" in b for b in engines.banners())
    assert llm.support_chat("p1") is None and llm.planner_chat("p1") is None


def test_keys_switch_the_engines_on(monkeypatch: pytest.MonkeyPatch) -> None:
    config.load()["mode"] = "production"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("SARVAM_API_KEY", "s")
    assert (engines.status()["writer"], engines.voice()) == ("claude", "sarvam")
    assert engines.banners() == []
    assert isinstance(tts.get("p1"), tts.SarvamTTS)
    assert llm.planner_chat("p1").model == config.load()["llm"]["planner_model"]


def test_prototype_mode_always_uses_kokoro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "s")
    assert engines.voice() == "kokoro"
