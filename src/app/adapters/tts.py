"""TTS adapter (D-07, D-23). Prototype: Kokoro-82M through kokoro-onnx, local and free.
Sarvam is the production adapter and is not built until production mode (D-19).
"""

import hashlib
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from app.core import config
from app.core.errors import FatalError

RATE = 24000
MODELS = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_SHA256 = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}


class TTS(Protocol):
    def synthesize(self, text: str) -> Any:
        """Mono float samples at RATE Hz for one sentence of written text."""
        ...


def spoken_parts(text: str, pronunciation: dict[str, Any]) -> list[tuple[str, bool]]:
    """Written text -> [(piece, is_phonemes)]: replacements applied, dictionary words phonemised."""
    for written, said in pronunciation.get("replace", {}).items():
        text = re.sub(re.escape(written), said, text, flags=re.IGNORECASE)
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


def get() -> TTS:
    cfg = config.load()
    if cfg["mode"] == "prototype" and cfg["tts"]["engine"] == "kokoro":
        return KokoroTTS(cfg["tts"], cfg["pronunciation"])
    raise FatalError("production TTS (Sarvam) is not built yet (D-19)")
