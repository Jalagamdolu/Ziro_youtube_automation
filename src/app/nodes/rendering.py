"""rendering: narration (TTS) → word alignment (WhisperX) → SRT/VTT → Remotion video → FFmpeg
loudness finishing → thumbnail + preview frame (§4, D-07, D-08).

Scenes come from storyboarding's scenes.json; their start/end are the exact times of the audio
synthesised for them. Shorts only for now (D-26); chapters and dead-air QA follow.
"""

import json
import re
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.adapters import aligner, stock, tts
from app.core import config, costs, db
from app.core.contracts import ContentPackage
from app.core.errors import FatalError
from app.core.models import AssetLicense
from app.nodes import script_checks
from app.nodes.context import Outputs, StageContext

SENTENCE_PAUSE, SECTION_PAUSE = 0.15, 0.35
END_CARD_SECONDS = 2.0  # voice.md: end card about 2 seconds
CUE_WORDS = 5  # short cues read well on a phone
# A sentence ends at . ? or ! even when a closing quote or bracket follows ('startup."').
SENTENCE_END = re.compile(r"[.!?][\"”’')]*$")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"”’')])\s+")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "remotion"


def rendering(ctx: StageContext) -> Outputs:
    import numpy as np  # worker image only (D-24)
    import soundfile as sf

    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    if package.brief.format != "short":
        raise FatalError("Remotion templates exist for Shorts only so far (D-26)")
    scenes: list[dict[str, Any]] = ctx.read_json("storyboarding", "scenes.json")
    pronunciation = config.load()["pronunciation"]
    voice = tts.get()

    audio: list[Any] = []
    segments: list[dict[str, Any]] = []
    clock, section, characters = 0.0, None, 0
    for scene in scenes:
        if section is not None and scene["section"] != section:
            audio.append(np.zeros(int(SECTION_PAUSE * tts.RATE), dtype=np.float32))
            clock += SECTION_PAUSE
        section, scene["start"] = scene["section"], clock
        for sentence in sentences([scene["text"]]):
            samples = voice.synthesize(sentence)
            length = len(samples) / tts.RATE
            segments.append({"text": tts.spoken_text(sentence, pronunciation), "written": sentence,
                             "start": clock, "end": clock + length})
            audio += [samples, np.zeros(int(SENTENCE_PAUSE * tts.RATE), dtype=np.float32)]
            clock += length + SENTENCE_PAUSE
            characters += len(sentence)
        if scene["visual_type"] == "end_card" and clock - scene["start"] < END_CARD_SECONDS:
            hold = scene["start"] + END_CARD_SECONDS - clock
            audio.append(np.zeros(int(hold * tts.RATE), dtype=np.float32))
            clock += hold
        scene["end"] = clock
    with db.session() as s, s.begin():
        costs.record_cost(s, ctx.project_id, "rendering", "kokoro-local", characters)

    narration = np.concatenate(audio)
    spoken = aligner.get().align(_resample(narration, tts.RATE, aligner.RATE), segments)
    words = written_words(spoken, segments)
    cues = make_cues(words)

    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / "public").mkdir()
        sf.write(work / "public" / "narration.wav", narration, tts.RATE)
        footage = backgrounds(ctx.project_id, package.brief.topic, scenes, work / "public")
        (work / "props.json").write_text(json.dumps({
            "title": package.brief.topic, "audio": "narration.wav", "duration": clock,
            "scenes": [{k: scene[k] for k in ("id", "visual_type", "start", "end", "props",
                                              "background", "background_seconds") if k in scene}
                       for scene in scenes],
            "cues": cues}), encoding="utf-8")
        _run(["npx", "remotion", "render", "src/index.ts", "Short", str(work / "raw.mp4"),
              f"--props={work / 'props.json'}", f"--public-dir={work / 'public'}"], TEMPLATES)
        _run(["ffmpeg", "-y", "-i", "raw.mp4", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
              "-movflags", "+faststart", "video.mp4"], work)
        (work / "thumb.txt").write_text(package.thumbnail_text, encoding="utf-8")
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0F131A:s=1280x720", "-frames:v", "1",
              "-vf", f"drawtext=fontfile={FONT}:textfile=thumb.txt:fontcolor=white:fontsize=120:"
                     "x=(w-text_w)/2:y=(h-text_h)/2", "thumbnail.png"], work)
        outputs: Outputs = {
            "narration.wav": (work / "public" / "narration.wav").read_bytes(),
            "words.json": json.dumps(words, indent=2, ensure_ascii=False),
            "captions.srt": to_srt(cues),
            "captions.vtt": to_vtt(cues),
            "scenes_timed.json": json.dumps(scenes, indent=2, ensure_ascii=False),
            "video.mp4": (work / "video.mp4").read_bytes(),
            "thumbnail.png": (work / "thumbnail.png").read_bytes(),
        }
        for kind in dict.fromkeys(s["visual_type"] for s in scenes):  # one still per scene type
            scene = next(s for s in scenes if s["visual_type"] == kind)
            moment = scene["start"] + 0.75 * (scene["end"] - scene["start"])
            name = f"preview_{kind}.png"
            _run(["ffmpeg", "-y", "-ss", f"{moment:.2f}", "-i", "video.mp4", "-frames:v", "1",
                  name], work)
            outputs[name] = (work / name).read_bytes()
        duration = _probe_seconds(work / "video.mp4")
    low, high = script_checks.RUNTIME[package.brief.format]
    outputs["qa_report.json"] = json.dumps({
        "duration_s": round(duration, 1), "duration_ok": low <= duration <= high,
        "resolution": "1080x1920", "loudness_target_lufs": -14, "words": len(words),
        "cues": len(cues), "scene_types": sorted({s["visual_type"] for s in scenes}),
        "stock": stock_checks(ctx.project_id, footage),
        "deferred": ["chapters", "dead-air"]}, indent=2)
    outputs["stock.json"] = json.dumps(footage, indent=2, ensure_ascii=False)
    return outputs


def backgrounds(project_id: str, topic: str, scenes: list[dict[str, Any]], public: Path
                ) -> dict[str, Any]:
    """Stock clips behind the scenes (D-33): fetched once, stored in the render's public dir,
    one license row each. No provider or no usable clip leaves the solid brand background."""
    providers = stock.get()
    query, clips, searches = stock.find(providers, stock.background_query(topic),
                                        config.load()["stock"]["clips_per_video"])
    if searches:
        costs.record_usage(project_id, "rendering", [(f"{providers[0].name}-search", searches)])
    for i, clip in enumerate(clips):
        (public / f"background_{i}.mp4").write_bytes(stock.download(clip))
    behind = [s for s in scenes if s["visual_type"] != "end_card"]  # the end card stays clean
    for i, scene in enumerate(behind if clips else []):
        scene["background"] = f"background_{i % len(clips)}.mp4"
        scene["background_seconds"] = clips[i % len(clips)].seconds
    with db.session() as s, s.begin():
        s.add_all(AssetLicense(asset=f"{c.provider} video {c.id}", type="stock_video",
                               source=c.page_url, license=c.license, proof_url=c.license_url,
                               project_id=project_id, query=query) for c in clips)
    provider = clips[0].provider.capitalize() if clips else None
    return {"query": query, "provider": provider, "clips": [asdict(c) for c in clips],
            "credit": f"Stock footage: {provider}" if clips else None}


def stock_checks(project_id: str, footage: dict[str, Any]) -> dict[str, Any]:
    """QA: every clip used has a license row for this run and no people or brand tags; any
    failure stops the stage rather than shipping unlicensed footage."""
    with db.session() as s:
        licensed = s.scalar(select(func.count()).where(AssetLicense.project_id == project_id,
                                                       AssetLicense.type == "stock_video")) or 0
    clips = footage["clips"]
    report = {"clips": len(clips), "query": footage["query"], "provider": footage["provider"],
              "all_licensed": licensed >= len(clips),
              "no_people_or_brand_tags": not any(stock.EXCLUDED.search(c["tags"]) for c in clips),
              "credit": footage["credit"]}
    if not (report["all_licensed"] and report["no_people_or_brand_tags"]):
        raise FatalError(f"stock footage failed QA: {report}")
    return report


def sentences(lines: list[str]) -> list[str]:
    text = " ".join(script_checks.MARKER.sub("", line).strip() for line in lines)
    return [s.strip() for s in SENTENCE_BREAK.split(text) if s.strip()]


def written_words(spoken: list[dict[str, Any]], segments: list[dict[str, Any]]
                  ) -> list[dict[str, Any]]:
    """Aligned spoken words back to the written script (captions show "ziro.digital", while the
    narrator said "Ziro dot digital"). Each written token takes the times of the spoken words it
    became."""
    words: list[dict[str, Any]] = []
    queue = list(spoken)
    pronunciation = config.load()["pronunciation"]
    for segment in segments:
        for token in segment["written"].split():
            said = len(tts.spoken_text(token, pronunciation).split())
            taken, queue = queue[:said], queue[said:]
            if taken:
                words.append({"text": token, "start": taken[0]["start"], "end": taken[-1]["end"]})
    return words


def make_cues(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cues of at most CUE_WORDS words that never span two sentences."""
    cues: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        if len(current) == CUE_WORDS or SENTENCE_END.search(word["text"]):
            cues.append({"start": current[0]["start"], "end": current[-1]["end"], "words": current})
            current = []
    if current:
        cues.append({"start": current[0]["start"], "end": current[-1]["end"], "words": current})
    return cues


def _stamp(t: float, sep: str) -> str:
    ms = round(t * 1000)
    hours, minutes, seconds = ms // 3_600_000, ms // 60_000 % 60, ms // 1000 % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{ms % 1000:03d}"


def to_srt(cues: list[dict[str, Any]]) -> str:
    return "\n".join(f"{i}\n{_stamp(c['start'], ',')} --> {_stamp(c['end'], ',')}\n"
                     f"{' '.join(w['text'] for w in c['words'])}\n" for i, c in enumerate(cues, 1))


def to_vtt(cues: list[dict[str, Any]]) -> str:
    return "WEBVTT\n\n" + "\n".join(
        f"{_stamp(c['start'], '.')} --> {_stamp(c['end'], '.')}\n"
        f"{' '.join(w['text'] for w in c['words'])}\n" for c in cues)


def _resample(samples: Any, rate: int, target: int) -> Any:
    import numpy as np

    n = int(len(samples) * target / rate)
    return np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)),
                     samples).astype(np.float32)


def _probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _run(command: list[str], cwd: Path) -> None:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise FatalError(f"{command[0]} {command[1]} failed: {done.stderr[-800:]}")
