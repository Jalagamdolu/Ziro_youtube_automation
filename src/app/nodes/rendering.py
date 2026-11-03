"""rendering: narration (TTS) → word alignment (WhisperX) → SRT/VTT → Remotion video → FFmpeg
loudness finishing → thumbnail + preview frame (§4, D-07, D-08).

Scenes come from storyboarding's scenes.json; their start/end are the exact times of the audio
synthesised for them. Shorts only for now (D-26); chapters and dead-air QA follow.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.adapters import aligner, stock, storage, tts
from app.core import config, costs, db
from app.core.contracts import ContentPackage
from app.core.errors import FatalError
from app.core.models import AssetLicense
from app.nodes import script_checks
from app.nodes.context import Outputs, StageContext

SENTENCE_PAUSE, SECTION_PAUSE = 0.15, 0.35
# The reviewer's photo swaps at qa_review (D-34): {scene id: candidate index}.
PHOTO_CHOICES = "{}/rendering/photo_choices.json"
END_CARD_SECONDS = 2.0  # voice.md: end card about 2 seconds
# A real presenter's recording of the approved script (D-36), uploaded on the run page.
RECORDING = "{}/recording/presenter.mp4"
WAITING_FOR_RECORDING = ("waiting for the presenter's recording: read the script on the run page, "
                         "record it on a phone and upload it there")
CARD_TYPES = {"definition_card", "quote_card", "flow", "checklist"}  # split screen with presenter
SHOT_SECONDS = 3.5  # cut roughly this often, at a word boundary (D-37)
CAPTURED = {"definition_card", "quote_card"}  # scenes whose cited source page is shown (D-37)
CUE_WORDS = 3  # 2-3 big words at a time, the Shorts caption style (D-37)
# A sentence ends at . ? or ! even when a closing quote or bracket follows ('startup."').
SENTENCE_END = re.compile(r"[.!?][\"”’')]*$")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"”’')])\s+")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "remotion"
# The official logo, used unaltered on the end card; its "#1" tagline is an approved fact (D-35).
LOGO = TEMPLATES.parent / "brand" / "ziro-digital-logo-transparent.png"
# Remotion's own headless Chrome (worker image), reused for source-page captures (D-37).
CHROME = TEMPLATES / ("node_modules/.remotion/chrome-headless-shell/linux64/"
                      "chrome-headless-shell-linux64/chrome-headless-shell")


def rendering(ctx: StageContext) -> Outputs:
    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    if package.brief.format != "short":
        raise FatalError("Remotion templates exist for Shorts only so far (D-26)")
    recording = RECORDING.format(ctx.project_id)
    if package.brief.presenter and not ctx.storage.exists(recording):
        raise FatalError(WAITING_FOR_RECORDING)
    import soundfile as sf  # worker image only (D-24)

    scenes: list[dict[str, Any]] = ctx.read_json("storyboarding", "scenes.json")
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / "public").mkdir()
        if package.brief.presenter:
            shutil.copyfile(config.runs_dir() / recording, work / "public" / "presenter.mp4")
            narration, segments, clock = _recorded(work / "public" / "presenter.mp4", scenes)
        else:
            narration, segments, clock = _synthesised(ctx.project_id, scenes)
        spoken = aligner.get().align(_resample(narration, tts.RATE, aligner.RATE), segments)
        words = written_words(spoken, segments)
        cues = make_cues(words)
        if package.brief.presenter:  # the recording's own timing decides where scenes fall
            scene_times(scenes, words, clock)
            set_layouts(scenes)
        sf.write(work / "public" / "narration.wav", narration, tts.RATE)
        footage = photos(ctx.project_id, scenes, work / "public")
        sources = captures(ctx.project_id, scenes, work / "public")
        plan_shots(scenes, words, package.brief.presenter)
        shutil.copyfile(LOGO, work / "public" / LOGO.name)
        for scene in scenes:
            if scene["visual_type"] == "end_card":
                scene["props"]["logo"] = LOGO.name
        (work / "props.json").write_text(json.dumps({
            "title": package.brief.topic, "audio": "narration.wav", "duration": clock,
            "presenter": "presenter.mp4" if package.brief.presenter else None,
            "scenes": [{k: scene[k] for k in ("id", "visual_type", "start", "end", "props",
                                              "photo", "layout", "capture", "shots")
                        if k in scene}
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
    # The finished video adds sentence and section pauses to the script's 150 wpm estimate.
    low, high = (round(package.brief.target_seconds * 0.75),
                 round(package.brief.target_seconds * 1.25))
    outputs["qa_report.json"] = json.dumps({
        "duration_s": round(duration, 1), "duration_ok": low <= duration <= high,
        "resolution": "1080x1920", "loudness_target_lufs": -14, "words": len(words),
        "cues": len(cues), "scene_types": sorted({s["visual_type"] for s in scenes}),
        "stock": stock_checks(ctx.project_id, footage),
        "source_captures": sources,
        "deferred": ["chapters", "dead-air"]}, indent=2)
    outputs["stock.json"] = json.dumps(footage, indent=2, ensure_ascii=False)
    return outputs


def _synthesised(project_id: str, scenes: list[dict[str, Any]]
                 ) -> tuple[Any, list[dict[str, Any]], float]:
    """Kokoro narration, one sentence at a time; scene start/end are the exact audio times."""
    import numpy as np  # worker image only (D-24)

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
        costs.record_cost(s, project_id, "rendering", "kokoro-local", characters)
    return np.concatenate(audio), segments, clock


def _recorded(video: Path, scenes: list[dict[str, Any]]
              ) -> tuple[Any, list[dict[str, Any]], float]:
    """The presenter's own voice from their recording (D-36): one segment covering the whole
    script, so WhisperX places every written word in the real audio."""
    import soundfile as sf

    wav = video.with_name("recorded.wav")
    _run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", str(tts.RATE), str(wav)],
         video.parent)
    narration, _ = sf.read(wav, dtype="float32")
    wav.unlink()
    clock = len(narration) / tts.RATE
    written = " ".join(sentence for scene in scenes for sentence in sentences([scene["text"]]))
    pronunciation = config.load()["pronunciation"]
    return narration, [{"text": tts.spoken_text(written, pronunciation), "written": written,
                        "start": 0.0, "end": clock}], clock


def scene_times(scenes: list[dict[str, Any]], words: list[dict[str, Any]], clock: float
                ) -> None:
    """Each scene starts at its first spoken word in the recording and runs to the next scene;
    if alignment lost words, scenes fall back to their share of the written words."""
    counts = [len(" ".join(sentences([s["text"]])).split()) for s in scenes]
    total, seen = sum(counts), 0
    for scene, count in zip(scenes, counts, strict=True):
        if len(words) >= total:
            scene["start"] = 0.0 if seen == 0 else words[seen]["start"]
        else:
            scene["start"] = clock * seen / max(1, total)
        seen += count
    for scene, following in zip(scenes, [*scenes[1:], None], strict=True):
        scene["end"] = following["start"] if following else clock


def set_layouts(scenes: list[dict[str, Any]]) -> None:
    """Presenter videos (D-36): the presenter fills the frame for the opening line; scenes with a
    card split the screen (card on top, presenter below); other scenes cut away to their photo
    while the presenter keeps talking. Only cut-aways search for a photo."""
    for i, scene in enumerate(scenes):
        if scene["visual_type"] == "end_card":
            continue
        if i == 0:
            scene["layout"] = "presenter"
        elif scene["visual_type"] in CARD_TYPES:
            scene["layout"] = "split"
        else:
            scene["layout"] = "photo" if scene.get("photo_query") else "presenter"
        if scene["layout"] != "photo":
            scene["photo_query"] = None


def captures(project_id: str, scenes: list[dict[str, Any]], public: Path) -> list[str]:
    """The real page each cited claim comes from (D-37): a tall screenshot taken with the headless
    Chrome Remotion already ships, scrolled to the quoted passage and highlighting it, then panned
    slowly on screen with the source credited. Genuine capture, never a mock-up; cached per URL and
    quote; a page that blocks, times out or renders blank just isn't shown."""
    store, shown = storage.get(), list[str]()
    if not CHROME.exists():  # only the worker image ships Remotion's headless Chrome
        return shown
    for scene in scenes:
        props = scene.get("props", {})
        url = props.get("source_url")
        if scene["visual_type"] not in CAPTURED or not url:
            continue
        quote = props.get("quote") or props.get("definition", "").strip("“”\"")
        key = f"_captures/{hashlib.sha256(f'{url} {quote}'.encode()).hexdigest()[:16]}.png"
        if not store.exists(key):
            shot = public / "capture.tmp.png"
            try:  # capture.mjs: DevTools-driven screenshot with the quote highlighted
                subprocess.run(["node", "capture.mjs", str(CHROME), url, str(shot), quote],
                               cwd=TEMPLATES, capture_output=True, timeout=70, check=False)
            except subprocess.TimeoutExpired:
                continue
            if not shot.exists() or shot.stat().st_size < 40_000:  # blank or blocked page
                shot.unlink(missing_ok=True)
                continue
            store.write(key, shot.read_bytes())
            shot.unlink()
        scene["capture"] = f"capture_{scene['id']}.png"
        (public / scene["capture"]).write_bytes(store.read(key))
        if url not in shown:
            shown.append(url)
    with db.session() as s, s.begin():
        s.add_all(AssetLicense(asset=f"screen capture of {url}", type="source_capture",
                               source=url, license="Screen capture of the cited source page, "
                               "shown briefly with attribution (D-37)", proof_url=url,
                               project_id=project_id) for url in shown)
    return shown


def plan_shots(scenes: list[dict[str, Any]], words: list[dict[str, Any]], presenter: bool
               ) -> None:
    """Cut each scene into shots of about SHOT_SECONDS, at word boundaries, alternating looks
    (D-37): a cited scene opens on its source page; then the card or photo alternates with the
    presenter (presenter videos) or with a second camera move on the photo (narrated videos)."""
    for i, scene in enumerate(scenes):
        start, end = scene["start"], scene["end"]
        if scene["visual_type"] == "end_card":
            scene["shots"] = [{"start": start, "end": end, "kind": "end", "card": True}]
            continue
        count = max(1, round((end - start) / SHOT_SECONDS))
        ends = [w["end"] for w in words if start < w["end"] < end]
        cuts = [start]
        for k in range(1, count):
            target = start + (end - start) * k / count
            cut = min(ends, key=lambda t: abs(t - target)) if ends else target
            if cut - cuts[-1] > 1.0:
                cuts.append(cut)
        cuts.append(end)
        kinds = _looks(scene, presenter, first=i == 0)
        scene["shots"] = [{"start": a, "end": b, "kind": kinds[n % len(kinds)],
                           "card": kinds[n % len(kinds)] in ("split", "photo", "photo_alt",
                                                              "card")}
                          for n, (a, b) in enumerate(zip(cuts, cuts[1:], strict=False))]


def _looks(scene: dict[str, Any], presenter: bool, first: bool) -> list[str]:
    capture = ["capture"] if scene.get("capture") else []
    if presenter:
        layout = scene.get("layout", "presenter")
        if layout == "photo" and scene.get("photo"):
            return ["photo", "presenter"]
        if first:  # a presenter video opens on the presenter's face
            return ["presenter", "split"]
        if layout == "split":
            return [*capture, "split", "presenter_zoom"]
        return ["presenter", "presenter_zoom"]
    base = ["photo", "photo_alt"] if scene.get("photo") else ["card"]
    return [*capture, *base]


def photos(project_id: str, scenes: list[dict[str, Any]], public: Path) -> dict[str, Any]:
    """One real photo per scene (D-34): the reviewer's swap choice if any, else the first
    candidate for the scene's search phrase; stored in the render's public dir, one license row
    each. No provider or no match leaves that scene on the solid brand background."""
    providers = stock.get()
    store = storage.get()
    chosen_key = PHOTO_CHOICES.format(project_id)
    choices = json.loads(store.read(chosen_key)) if store.exists(chosen_key) else {}
    report: list[dict[str, Any]] = []
    used: list[tuple[stock.Photo, str]] = []  # (photo, its search phrase)
    searches = 0
    for scene in scenes:
        if not (scene.get("photo_query") and providers):
            continue
        found, made = stock.candidates(providers, scene["photo_query"])
        searches += made
        if not found:
            continue
        taken = {photo.id for photo, _ in used}  # no photo twice in one video
        fresh = [i for i, c in enumerate(found) if c.id not in taken] or [0]
        pick = (min(int(choices[scene["id"]]), len(found) - 1) if scene["id"] in choices
                else fresh[0])  # the reviewer's swap always wins
        scene["photo"] = f"photo_{scene['id']}.jpg"
        (public / scene["photo"]).write_bytes(stock.download(found[pick]))
        used.append((found[pick], scene["photo_query"]))
        report.append({"scene": scene["id"], "query": scene["photo_query"], "chosen": pick,
                       "candidates": [asdict(c) for c in found]})
    if searches:
        costs.record_usage(project_id, "rendering", [(f"{providers[0].name}-search", searches)])
    with db.session() as s, s.begin():
        s.add_all(AssetLicense(asset=f"{p.provider} photo {p.id}", type="stock_photo",
                               source=p.page_url, license=p.license, proof_url=p.license_url,
                               project_id=project_id, query=query) for p, query in used)
    provider = used[0][0].provider.capitalize() if used else None
    return {"provider": provider, "scenes": report,
            "credit": f"Images: {provider}" if used else None}


def stock_checks(project_id: str, footage: dict[str, Any]) -> dict[str, Any]:
    """QA: every photo used has a license row for this run, and none is tagged with faces,
    minors or brands; a failure stops the stage rather than shipping it."""
    with db.session() as s:
        licensed = s.scalar(select(func.count()).where(AssetLicense.project_id == project_id,
                                                       AssetLicense.type == "stock_photo")) or 0
    chosen = [r["candidates"][r["chosen"]] for r in footage["scenes"]]
    report = {"photos": len(chosen), "provider": footage["provider"],
              "all_licensed": licensed >= len(chosen),
              "no_faces_minors_or_brands": not any(stock.EXCLUDED.search(c["tags"])
                                                   for c in chosen),
              "credit": footage["credit"]}
    if not (report["all_licensed"] and report["no_faces_minors_or_brands"]):
        raise FatalError(f"stock photos failed QA: {report}")
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
