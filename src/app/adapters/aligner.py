"""Aligner adapter (D-07): word timings come from our own forced alignment, not the TTS vendor.

Input is the narration at 16 kHz plus the sentences we synthesised, with their exact start/end
times, so WhisperX only has to place known words inside known windows.
"""

from typing import Any, Protocol

RATE = 16000


class Aligner(Protocol):
    def align(self, audio: Any, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """segments: [{text, start, end}] -> words: [{text, start, end}] in order."""
        ...


class WhisperXAligner:
    def __init__(self) -> None:
        import whisperx  # worker image only (D-24)

        self.whisperx = whisperx
        self.model, self.metadata = whisperx.load_align_model(language_code="en", device="cpu")

    def align(self, audio: Any, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = self.whisperx.align(
            [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in segments],
            self.model, self.metadata, audio, "cpu", return_char_alignments=False)
        words: list[dict[str, Any]] = []
        for segment, aligned in zip(segments, result["segments"], strict=True):
            found = aligned.get("words", [])
            # Tokens the model cannot place (e.g. digits) inherit their neighbours' times.
            for i, word in enumerate(found):
                start = word.get("start", found[i - 1]["end"] if i else segment["start"])
                end = word.get("end", start)
                words.append({"text": word["word"], "start": float(start), "end": float(end)})
        return words


class EvenAligner:
    """Spreads each sentence's words over its window by character share (tests, fallback)."""

    def align(self, audio: Any, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        words: list[dict[str, Any]] = []
        for segment in segments:
            tokens = segment["text"].split()
            total = sum(len(t) for t in tokens)
            t = segment["start"]
            for token in tokens:
                step = (segment["end"] - segment["start"]) * len(token) / total
                words.append({"text": token, "start": t, "end": t + step})
                t += step
        return words


def get() -> Aligner:
    return WhisperXAligner()
