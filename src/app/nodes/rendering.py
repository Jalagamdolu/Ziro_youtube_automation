"""rendering (demo triage, D-25): narration WAV, SRT captions, MP4 and thumbnail with FFmpeg.

Each sentence is synthesised on its own, so caption times come from the exact length of the audio
we generated. WhisperX word alignment, VTT, chapters, dead-air QA and Remotion templates follow
after the demo.
"""

import json
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from app.adapters import tts
from app.core import costs, db
from app.core.contracts import ContentPackage
from app.nodes import script_checks
from app.nodes.context import Outputs, StageContext

SENTENCE_PAUSE, SECTION_PAUSE = 0.15, 0.35
CUE_WORDS = 5  # short cues read well on a phone
SIZE = {"short": (1080, 1920), "long": (1920, 1080)}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def rendering(ctx: StageContext) -> Outputs:
    import numpy as np  # worker image only (D-24)
    import soundfile as sf

    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    voice = tts.get()
    audio: list[Any] = []
    cues: list[tuple[float, float, str]] = []
    clock, characters = 0.0, 0
    for lines in script_checks.sections(package.script).values():
        for sentence in sentences(lines):
            samples = voice.synthesize(sentence)
            length = len(samples) / tts.RATE
            cues += split_cue(clock, clock + length, sentence)
            audio += [samples, np.zeros(int(SENTENCE_PAUSE * tts.RATE), dtype=np.float32)]
            clock += length + SENTENCE_PAUSE
            characters += len(sentence)
        audio.append(np.zeros(int(SECTION_PAUSE * tts.RATE), dtype=np.float32))
        clock += SECTION_PAUSE
    with db.session() as s, s.begin():
        costs.record_cost(s, ctx.project_id, "rendering", "kokoro-local", characters)

    width, height = SIZE[package.brief.format]
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        sf.write(work / "narration.wav", np.concatenate(audio), tts.RATE)
        (work / "captions.srt").write_text(to_srt(cues), encoding="utf-8")
        (work / "title.txt").write_text(textwrap.fill(package.brief.topic, 24), encoding="utf-8")
        (work / "thumb.txt").write_text(package.thumbnail_text, encoding="utf-8")
        _ffmpeg(work, width, height)
        duration = _probe_seconds(work / "video.mp4")
        low, high = script_checks.RUNTIME[package.brief.format]
        report = {"duration_s": round(duration, 1), "duration_ok": low <= duration <= high,
                  "resolution": f"{width}x{height}", "loudness_target_lufs": -14,
                  "cues": len(cues), "deferred": ["chapters", "dead-air", "vtt", "end card"]}
        return {
            "narration.wav": (work / "narration.wav").read_bytes(),
            "captions.srt": (work / "captions.srt").read_text(encoding="utf-8"),
            "video.mp4": (work / "video.mp4").read_bytes(),
            "thumbnail.png": (work / "thumbnail.png").read_bytes(),
            "qa_report.json": json.dumps(report, indent=2),
        }


def sentences(lines: list[str]) -> list[str]:
    text = " ".join(script_checks.MARKER.sub("", line).strip() for line in lines)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def split_cue(start: float, end: float, sentence: str) -> list[tuple[float, float, str]]:
    """One sentence -> cues of at most CUE_WORDS words, timed by their share of the characters."""
    words = sentence.split()
    chunks = [" ".join(words[i:i + CUE_WORDS]) for i in range(0, len(words), CUE_WORDS)]
    total = sum(len(c) for c in chunks)
    cues, t = [], start
    for chunk in chunks:
        step = (end - start) * len(chunk) / total
        cues.append((t, t + step, chunk))
        t += step
    return cues


def to_srt(cues: list[tuple[float, float, str]]) -> str:
    def stamp(t: float) -> str:
        ms = round(t * 1000)
        hours, minutes, seconds = ms // 3_600_000, ms // 60_000 % 60, ms // 1000 % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms % 1000:03d}"

    return "\n".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n"
                     for i, (a, b, text) in enumerate(cues, 1))


def _ffmpeg(work: Path, width: int, height: int) -> None:
    style = ("FontName=DejaVu Sans,Bold=1,FontSize=11,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=60")
    video = (f"[0:v]drawtext=fontfile={FONT}:textfile=title.txt:fontcolor=white:fontsize="
             f"{width // 16}:line_spacing=12:x=(w-text_w)/2:y=h*0.12,"
             f"subtitles=captions.srt:force_style='{style}'[v]")
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0f172a:s={width}x{height}:r=30",
          "-i", "narration.wav", "-filter_complex",
          f"{video};[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]", "-map", "[v]", "-map", "[a]",
          "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
          "-movflags", "+faststart", "video.mp4"], work)
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0f172a:s=1280x720", "-frames:v", "1",
          "-vf", f"drawtext=fontfile={FONT}:textfile=thumb.txt:fontcolor=white:fontsize=120:"
                 "x=(w-text_w)/2:y=(h-text_h)/2", "thumbnail.png"], work)


def _probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, capture_output=True, check=True, timeout=900)
