"""rendering: narration (TTS, one cached WAV per beat at -14 LUFS) → word alignment (WhisperX) →
SRT/VTT → Remotion split-layout Short → FFmpeg loudness finishing → thumbnail + previews → QA
(§4, D-07, D-08, D-46, D-48).

Scenes come from storyboarding's scenes.json; their start/end are the exact times of the audio
synthesised for them. Shorts only for now (D-26); chapters and dead-air QA follow.
"""

import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.adapters import aligner, stock, storage, tts
from app.core import config, costs, db, engines
from app.core.contracts import ContentPackage
from app.core.errors import FatalError
from app.core.models import AssetLicense
from app.nodes import script_checks
from app.nodes.context import Outputs, StageContext

SENTENCE_PAUSE, SECTION_PAUSE = script_checks.SENTENCE_PAUSE, script_checks.SECTION_PAUSE
TIGHT_PAUSES = (0.05, 0.12)  # used only when the normal pauses would pass a Short's length (D-62)
# The reviewer's photo swaps at qa_review (D-34): {scene id: candidate index}.
PHOTO_CHOICES = "{}/rendering/photo_choices.json"
END_CARD_SECONDS = 2.0  # voice.md: end card about 2 seconds
# A visual change every 2-4 s (v2 §8, D-48): shots aim under SHOT_MAX and snap to a word end
# at most SNAP away, so none passes PACE's ceiling; QA measures the result.
SHOT_MAX, SNAP, PACE = 3.6, 0.3, (2.0, 4.0)
CAPTURED = {"definition_card", "quote_card"}  # scenes whose cited source page can be shown (D-37)
CAPTURE_VERSION = 2  # 2: adverts and popups hidden (D-59); a new version re-captures every page
CUE_WORDS = 7  # the small transcription box: two short lines at a time (D-48)
LOUDNESS = (-15.5, -12.5)  # integrated LUFS the finished video must land in (target -14)
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
    import soundfile as sf  # worker image only (D-24)

    scenes: list[dict[str, Any]] = ctx.read_json("storyboarding", "scenes.json")
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / "public").mkdir()
        # A Short's requested length is a ceiling (D-62); a long video keeps its ±25% QA band.
        progress(ctx.project_id, "voice")
        narration, segments, clock = _synthesised(ctx.project_id, scenes,
                                                  package.brief.target_seconds)
        progress(ctx.project_id, "captions")
        spoken = aligner.get().align(_resample(narration, tts.RATE, aligner.RATE), segments)
        words = written_words(spoken, segments)
        cues = make_cues(words)
        sf.write(work / "public" / "narration.wav", narration, tts.RATE)
        footage = photos(ctx.project_id, scenes, work / "public")
        sources = captures(ctx.project_id, scenes, work / "public")
        plan_shots(scenes, words)
        echoes = echo_track(scenes)
        pace = pacing(scenes)
        if not pace["ok"]:
            raise FatalError(f"pacing QA failed: {pace}")
        shutil.copyfile(LOGO, work / "public" / LOGO.name)  # the end card only (D-35, D-57)
        for scene in scenes:
            if scene["visual_type"] == "end_card":
                scene["props"]["logo"] = LOGO.name
        (work / "props.json").write_text(json.dumps({
            "title": package.brief.topic, "audio": "narration.wav", "duration": clock,
            "presenter": {"clip": None},  # sir's clip drops in here once it exists (D-57)
            "scenes": [{k: scene[k] for k in ("id", "visual_type", "start", "end", "props",
                                              "photo", "capture", "shots", "pop")
                        if k in scene}
                       for scene in scenes],
            "cues": cues, "echoes": echoes}), encoding="utf-8")
        progress(ctx.project_id, "render")
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
        progress(ctx.project_id, "quality")
        duration = _probe_seconds(work / "video.mp4")
        lufs = _loudness(work / "video.mp4")
    # A Short's requested length is a ceiling (D-62): up to 15% under is fine, over fails QA
    # (0.1 s for the container's frame rounding). Scripting already counts the pauses.
    target = package.brief.target_seconds
    low, high = round(target * (1 - script_checks.TOLERANCE)), target
    if duration > target + 0.1:
        raise FatalError(f"the Short runs {duration:.1f}s but was asked for at most {target}s, "
                         "even with the pauses tightened. Reject to scripting to cut words.")
    outputs["qa_report.json"] = json.dumps({
        "duration_s": round(duration, 1), "duration_ok": low <= duration <= high,
        "resolution": "1080x1920", "layout": "split (D-48)", "voice": engines.voice(),
        "loudness_lufs": lufs, "loudness_ok": LOUDNESS[0] <= lufs <= LOUDNESS[1],
        "pacing": pace, "words": len(words), "cues": len(cues), "echoes": len(echoes),
        "text_pops": sum(1 for s in scenes if s.get("pop")),
        "scene_types": sorted({s["visual_type"] for s in scenes}),
        "stock": stock_checks(ctx.project_id, footage),
        "source_captures": sources,
        "presenter": "placeholder: sir's zone, silhouette (clip not supplied yet, D-57)",
        "deferred": ["chapters", "dead-air", "lip-sync (LatentSync)"]}, indent=2)
    outputs["stock.json"] = json.dumps(footage, indent=2, ensure_ascii=False)
    return outputs


STEPS = ("voice", "captions", "render", "quality")  # what the Generating screen shows (D-69)


def progress(project_id: str, step: str) -> None:
    """Which step the render is on, for the live Generating screen; not an artifact."""
    data = json.dumps({"step": step}).encode()
    storage.get().write(f"{project_id}/rendering/progress.json", data)


def _synthesised(project_id: str, scenes: list[dict[str, Any]], ceiling: float | None = None
                 ) -> tuple[Any, list[dict[str, Any]], float]:
    """Narration one beat (scene) at a time; scene start/end and scene["timed"] (one entry per
    sentence) are the exact audio times. Each beat is one WAV at -14 LUFS, cached by its text
    and voice settings, so a re-render (photo swap, QA reject) never pays for speech twice.
    Past `ceiling` (a Short's requested length, D-62) the pauses tighten, cut from the same
    audio; QA fails whatever still runs over."""
    voice, store = tts.get(project_id), storage.get()
    beats, characters = [], 0
    for scene in scenes:
        lines = sentences([scene["text"]])
        beat, lengths, made = _beat(voice, store, lines)
        beats.append((lines, beat, lengths))
        characters += made
    with db.session() as s, s.begin():
        costs.record_cost(s, project_id, "rendering", voice.name, characters)
    for pauses in ((SENTENCE_PAUSE, SECTION_PAUSE), TIGHT_PAUSES):
        assembled = _assemble(scenes, beats, *pauses)
        if ceiling is None or assembled[2] <= ceiling:
            break
    return assembled


def _assemble(scenes: list[dict[str, Any]], beats: list[tuple[list[str], Any, list[float]]],
              sentence_pause: float, section_pause: float
              ) -> tuple[Any, list[dict[str, Any]], float]:
    """The narration track with these pauses; sets each scene's start, end and timed sentences."""
    import numpy as np  # worker image only (D-24)

    pronunciation = config.load()["pronunciation"]
    audio: list[Any] = []
    segments: list[dict[str, Any]] = []
    clock, section = 0.0, None
    for scene, (lines, beat, lengths) in zip(scenes, beats, strict=True):
        if section is not None and scene["section"] != section:
            audio.append(np.zeros(int(section_pause * tts.RATE), dtype=np.float32))
            clock += section_pause
        section, scene["start"] = scene["section"], clock
        beat = _respaced(beat, lengths, sentence_pause)
        scene["timed"] = []
        for sentence, length in zip(lines, lengths, strict=True):
            segments.append({"text": tts.spoken_text(sentence, pronunciation), "written": sentence,
                             "start": clock, "end": clock + length})
            scene["timed"].append({"text": sentence, "start": clock, "end": clock + length})
            clock += length + sentence_pause
        audio.append(beat)
        clock = scene["start"] + len(beat) / tts.RATE
        if scene["visual_type"] == "end_card" and clock - scene["start"] < END_CARD_SECONDS:
            hold = scene["start"] + END_CARD_SECONDS - clock
            audio.append(np.zeros(int(hold * tts.RATE), dtype=np.float32))
            clock += hold
        scene["end"] = clock
    return np.concatenate(audio), segments, clock


def _respaced(beat: Any, lengths: list[float], pause: float) -> Any:
    """A cached beat (each sentence followed by SENTENCE_PAUSE of silence) with `pause` instead:
    the sentences are cut out of the same audio, nothing is re-synthesised."""
    import numpy as np

    if pause == SENTENCE_PAUSE:
        return beat
    gap, start, parts = int(SENTENCE_PAUSE * tts.RATE), 0, []
    for length in lengths:
        n = round(length * tts.RATE)
        parts += [beat[start:start + n], np.zeros(int(pause * tts.RATE), dtype=np.float32)]
        start += n + gap
    return np.concatenate(parts) if parts else beat


def _beat(voice: tts.TTS, store: storage.Storage, lines: list[str]
          ) -> tuple[Any, list[float], int]:
    """(beat samples incl. a pause after each sentence, sentence lengths in s, characters newly
    synthesised). Cached under _tts/ by voice settings + text."""
    import numpy as np
    import soundfile as sf

    key = "_tts/" + hashlib.sha256(json.dumps([voice.settings_key(), lines]).encode()
                                   ).hexdigest()[:20]
    if store.exists(f"{key}.wav") and store.exists(f"{key}.json"):
        samples, _ = sf.read(io.BytesIO(store.read(f"{key}.wav")), dtype="float32")
        return samples, json.loads(store.read(f"{key}.json")), 0
    pause = np.zeros(int(SENTENCE_PAUSE * tts.RATE), dtype=np.float32)
    pieces = [voice.synthesize(line) for line in lines]
    raw = np.concatenate([part for piece in pieces for part in (piece, pause)] or [pause])
    beat = _normalised(raw)
    lengths = [len(piece) / tts.RATE for piece in pieces]
    buffer = io.BytesIO()
    sf.write(buffer, beat, tts.RATE, format="WAV")
    store.write(f"{key}.wav", buffer.getvalue())
    store.write(f"{key}.json", json.dumps(lengths).encode())
    return beat, lengths, sum(len(line) for line in lines)


def _normalised(samples: Any) -> Any:
    """One beat at -14 LUFS (v2 §4 stage 6), same length; FFmpeg's loudnorm."""
    import numpy as np
    import soundfile as sf

    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        sf.write(work / "in.wav", samples, tts.RATE)
        _run(["ffmpeg", "-y", "-i", "in.wav", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
              "-ar", str(tts.RATE), "-ac", "1", "out.wav"], work)
        normalised, _ = sf.read(work / "out.wav", dtype="float32")
    if len(normalised) < len(samples):
        normalised = np.pad(normalised, (0, len(samples) - len(normalised)))
    return normalised[:len(samples)]


def captures(project_id: str, scenes: list[dict[str, Any]], public: Path) -> list[str]:
    """The real page each cited claim comes from (D-37): a tall screenshot taken with the headless
    Chrome Remotion already ships, scrolled to the quoted passage and highlighting it, then panned
    slowly on screen with the source credited. Genuine capture, never a mock-up; cached per URL and
    quote; a page that blocks, times out or renders blank just isn't shown. One source-proof
    shot per video (D-48): the first cited scene whose page captures."""
    store, shown = storage.get(), list[str]()
    if not CHROME.exists():  # only the worker image ships Remotion's headless Chrome
        return shown
    for scene in scenes:
        props = scene.get("props", {})
        url = props.get("source_url")
        if scene["visual_type"] not in CAPTURED or not url or shown:
            continue
        quote = props.get("quote") or props.get("definition", "").strip("“”\"")
        digest = hashlib.sha256(f"{CAPTURE_VERSION} {url} {quote}".encode()).hexdigest()[:16]
        key = f"_captures/{digest}.png"
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


def plan_shots(scenes: list[dict[str, Any]], words: list[dict[str, Any]]) -> None:
    """The split-layout timeline (v2 §8, D-48). Each shot has a layout and a kind:
    - FULL (presenter zone full screen): the Hook ("presenter"), a text pop ("pop") and the
      close: an engagement question on the presenter, then the end card ("end").
    - SPLIT (content top ~60%, presenter zone bottom ~40%): the body. Looks alternate: the
      source-proof capture once per video, then the scene's photo and card (or two framings of
      the card when the scene has no photo).
    Shots stay under SHOT_MAX and cut at word ends, so the picture changes every 2-4 s. The
    silence between beats belongs to the beat before it."""
    ends = [w["end"] for w in words]
    proof_shown = False
    for i, scene in enumerate(scenes):
        if i + 1 < len(scenes):
            scene["end"] = max(scene["end"], scenes[i + 1]["start"])
        a, b = scene["start"], scene["end"]
        timed = scene.get("timed") or [{"start": a, "end": b}]
        if scene["visual_type"] == "end_card":
            shots = _chunks(a, timed[-1]["start"], ends, ["presenter", "presenter_alt"], "full")
            shots.append({"start": timed[-1]["start"], "end": b, "kind": "end",
                          "layout": "full"})
        elif scene["section"] == "Hook":
            shots = _chunks(a, b, ends, ["presenter", "presenter_alt"], "full")
        else:
            looks = (["capture"] if scene.get("capture") and not proof_shown else []) + (
                ["photo", "card"] if scene.get("photo") else ["card", "card_alt"])
            spans = [(a, b, looks)]
            if pop := scene.get("pop"):
                k = pop["sentence"]
                top = timed[k]["start"]
                end = timed[k + 1]["start"] if k + 1 < len(timed) else b
                spans = [(a, top, looks), (top, end, ["pop"]), (end, b, looks)]
            shots = []
            for x, y, kinds in spans:
                if kinds != ["pop"] and any(s["kind"] == "capture" for s in shots):
                    kinds = [k for k in kinds if k != "capture"]
                shots += _chunks(x, y, ends, kinds, "full" if kinds == ["pop"] else "split")
        for shot in shots:
            shot["card"] = shot["kind"] in ("card", "card_alt")
        proof_shown = proof_shown or any(s["kind"] == "capture" for s in shots)
        scene["shots"] = shots


def _chunks(a: float, b: float, ends: list[float], kinds: list[str], layout: str
            ) -> list[dict[str, Any]]:
    """[a, b) cut into shots under SHOT_MAX at the nearest word end (within SNAP), kinds in
    turn; the capture, if listed first, only opens."""
    if b - a < 0.05:
        return []
    count = max(1, math.ceil((b - a) / SHOT_MAX))
    cuts = [a]
    for k in range(1, count):
        target = a + (b - a) * k / count
        near = [t for t in ends if abs(t - target) <= SNAP and t - cuts[-1] > 1.0]
        cuts.append(min(near, key=lambda t: abs(t - target)) if near else target)
    cuts.append(b)
    first, rest = (kinds[0], kinds[1:]) if kinds[0] == "capture" and len(kinds) > 1 \
        else (None, kinds)
    shots = []
    for n, (x, y) in enumerate(zip(cuts, cuts[1:], strict=False)):
        kind = first if n == 0 and first else rest[(n - (1 if first else 0)) % len(rest)]
        shots.append({"start": x, "end": y, "kind": kind, "layout": layout})
    return shots


def echo_track(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The big phrase on the divider (D-48): one per sentence, from the shot plan; every third
    in the brand colour. Not shown under a text pop or the end card, which carry their own."""
    track: list[dict[str, Any]] = []
    for scene in scenes:
        pop = scene.get("pop")
        last = len(scene.get("timed", [])) - 1
        for k, (line, phrase) in enumerate(zip(scene.get("timed", []), scene.get("echo", []),
                                               strict=False)):
            if (pop and pop["sentence"] == k) or (scene["visual_type"] == "end_card"
                                                   and k == last):
                continue
            track.append({"start": line["start"], "end": line["end"], "text": phrase,
                          "brand": len(track) % 3 == 2})
    return track


def pacing(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    """QA (D-48): how long the picture holds between changes. The closing end card is exempt."""
    held = [s["end"] - s["start"] for scene in scenes for s in scene["shots"]
            if s["kind"] != "end"]
    longest = max(held, default=0.0)
    return {"shots": len(held) + 1, "longest_s": round(longest, 2),
            "shortest_s": round(min(held, default=0.0), 2),
            "under_2s": sum(1 for h in held if h < PACE[0]),  # short beats; reported, not failed
            "ok": longest <= PACE[1] + 0.25, "rule": "a visual change every 2-4 s"}


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


def _loudness(path: Path) -> float:
    """Integrated loudness (LUFS) of the finished video, from FFmpeg's EBU R128 meter."""
    done = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null",
                           "-"], capture_output=True, text=True, check=True)
    found = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", done.stderr)
    return float(found[-1]) if found else float("nan")


def _probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _run(command: list[str], cwd: Path) -> None:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise FatalError(f"{command[0]} {command[1]} failed: {done.stderr[-800:]}")
