"""TTS adapter (D-07, D-23, D-46). Production mode with SARVAM_API_KEY: Sarvam (paid, sir's voice
later). Otherwise Kokoro-82M through kokoro-onnx, local and free: prototype mode, tests, and the
fallback when there is no Sarvam key.
"""

import base64
import hashlib
import io
import os
import random
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core import config, costs, engines
from app.core.errors import FatalError, RetryableError
from app.core.log import log

RATE = 24000
MODELS = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_SHA256 = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}


SARVAM = "https://api.sarvam.ai/text-to-speech"


class TTS(Protocol):
    name: str  # cost-row price key: characters synthesised

    def synthesize(self, text: str) -> Any:
        """Mono float samples at RATE Hz for one sentence of written text."""
        ...

    def settings_key(self) -> str:
        """Everything that changes the sound, for the per-beat audio cache."""
        ...


def spoken_text(text: str, pronunciation: dict[str, Any]) -> str:
    """Written text as the narrator says it, in words (e.g. ziro.digital -> Ziro dot digital)."""
    for written, said in pronunciation.get("replace", {}).items():
        text = re.sub(re.escape(written), said, text, flags=re.IGNORECASE)
    return text


def spoken_parts(text: str, pronunciation: dict[str, Any]) -> list[tuple[str, bool]]:
    """Written text -> [(piece, is_phonemes)]: replacements applied, dictionary words phonemised."""
    text = spoken_text(text, pronunciation)
    words = pronunciation.get("phonemes", {})
    if not words:
        return [(text, False)]
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.IGNORECASE)
    parts: list[tuple[str, bool]] = []
    for i, piece in enumerate(pattern.split(text)):
        if i % 2:
            parts.append((next(v for k, v in words.items() if k.lower() == piece.lower()), True))
        elif piece.strip():
            parts.append((piece, False))
    return parts


class KokoroTTS:
    name = "kokoro-local"

    def __init__(self, settings: dict[str, Any], pronunciation: dict[str, Any]) -> None:
        from kokoro_onnx import Kokoro  # worker image only (D-24)

        folder = Path(os.environ.get("MODELS_DIR", "/models")) / "kokoro"
        self.engine = Kokoro(*(str(_model(folder, name)) for name in MODEL_SHA256))
        self.settings, self.pronunciation = settings, pronunciation

    def synthesize(self, text: str) -> Any:
        lang = self.settings["phonemes"]
        phonemes = " ".join(piece if is_ph else self.engine.tokenizer.phonemize(piece, lang)
                            for piece, is_ph in spoken_parts(text, self.pronunciation))
        samples, _ = self.engine.create(phonemes, voice=self.settings["voice"],
                                        speed=self.settings["speed"], lang=lang, is_phonemes=True)
        return samples

    def settings_key(self) -> str:
        return repr(("kokoro", self.settings["voice"], self.settings["speed"],
                     sorted(self.pronunciation.get("phonemes", {}).items())))


class SarvamTTS:
    """Sarvam text-to-speech (D-46): one request per sentence, WAV at RATE Hz, retried on 429,
    5xx and timeouts; every call checked against the daily budget first (D-45)."""

    name = "sarvam-tts-characters"

    def __init__(self, settings: dict[str, Any], pronunciation: dict[str, Any], key: str,
                 project_id: str | None) -> None:
        self.settings, self.pronunciation, self.key = settings, pronunciation, key
        self.project_id = project_id

    def said(self, text: str) -> str:
        """What Sarvam reads: replacements applied, brand words spelled as spoken (Zyro)."""
        text = spoken_text(text, self.pronunciation)
        for written, spelled in self.settings.get("spelling", {}).items():
            text = re.sub(rf"\b{re.escape(written)}\b", spelled, text, flags=re.IGNORECASE)
        return text

    def synthesize(self, text: str) -> Any:
        import soundfile as sf  # worker image only (D-24)

        samples, rate = sf.read(io.BytesIO(self.wav(text)), dtype="float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if rate != RATE:
            raise FatalError(f"sarvam returned {rate} Hz audio, asked for {RATE}")
        return samples

    def wav(self, text: str) -> bytes:
        """One sentence as WAV bytes: budget checked first, retried on 429 / 5xx / timeouts."""
        price = float(config.load()["prices"][self.name])
        costs.check_budget(self.project_id, 0, len(text) * price, [])
        body = {"text": self.said(text), "language_code": self.settings["language_code"],
                "model": self.settings["model"], "speaker": self.settings["speaker"],
                "pace": self.settings["pace"], "speech_sample_rate": RATE}
        attempts = self.settings["attempts"]
        for attempt in range(1, attempts + 1):
            try:
                return base64.b64decode(self._post(body)["audios"][0])
            except RetryableError as error:
                if attempt == attempts:
                    raise
                log.warning("sarvam retry", attempt=attempt, reason=str(error))
                time.sleep(min(30.0, 2 ** attempt) + random.random())
        raise FatalError("sarvam: no attempts configured")

    def _post(self, body: dict[str, Any]) -> Any:
        try:
            response = httpx.post(SARVAM, json=body, timeout=60.0,
                                  headers={"api-subscription-key": self.key})
        except httpx.TransportError as error:
            raise RetryableError(f"sarvam unreachable: {type(error).__name__}") from error
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableError(f"sarvam returned {response.status_code}")
        if response.status_code >= 400:  # bad key, bad voice, bad text: retrying won't help
            raise FatalError(f"sarvam returned {response.status_code}: {response.text[:300]}")
        return response.json()

    def settings_key(self) -> str:
        return repr(("sarvam", sorted((k, str(v)) for k, v in self.settings.items())))


def _model(folder: Path, name: str) -> Path:
    path = folder / name
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODELS + name, path.with_suffix(".part"))
        path.with_suffix(".part").rename(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256[name]:
        path.unlink()
        raise FatalError(f"{name} failed its SHA-256 check")
    return path


def get(project_id: str | None = None) -> TTS:
    cfg = config.load()
    if engines.voice() == "sarvam":
        return SarvamTTS(cfg["tts"]["sarvam"], cfg["pronunciation"],
                         os.environ["SARVAM_API_KEY"], project_id)
    return KokoroTTS(cfg["tts"], cfg["pronunciation"])
