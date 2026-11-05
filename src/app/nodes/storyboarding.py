"""storyboarding: each `[ON SCREEN: ...]` beat + the narration under it becomes one scene (§4).

The script is parsed deterministically; template text comes only from the script and the approved
claim ledger. A scene gets a photo search phrase (D-34) only when the LLM (or the prototype
fixture) names a literal, photographable subject; abstract scenes show their card or diagram on the
brand background (D-40). The reviewer approves the photos themselves at qa_review.
"""

import json
import re
from typing import Any

from app.adapters import llm, stock
from app.core import costs
from app.core.contracts import Claim, ContentPackage
from app.core.log import log
from app.nodes import script_checks
from app.nodes.context import Outputs, StageContext

# Beat description keyword -> Remotion template (templates/remotion/src/Short.tsx).
VISUAL_TYPES = [
    ("definition card", "definition_card"),
    ("quote card", "quote_card"),
    ("checklist", "checklist"),
    ("chat bubble", "chat_bubble"),
    ("flow", "flow"),
    ("side by side", "comparison"),
    ("logo", "end_card"),
]
QUOTED = re.compile(r'"([^"]+)"')
# Cards that are the visual themselves: never a photo behind them (D-40).
DIAGRAMS = {"definition_card", "quote_card", "flow", "checklist", "end_card"}
# Fields a template cannot render without; scripting rejects beats that leave them empty.
REQUIRED = {"definition_card": "definition", "quote_card": "definition", "comparison": "right",
            "chat_bubble": "message", "flow": "steps", "checklist": "items", "end_card": "url"}


def storyboarding(ctx: StageContext) -> Outputs:
    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    scenes = parse(package.script, package.claims)
    writer = llm.get("storyboarding")
    try:
        suggested = writer.photo_queries(package.brief, scenes)
    finally:
        costs.record_usage(ctx.project_id, "storyboarding", writer.calls)
    if len(suggested) != len(scenes):
        suggested = [""] * len(scenes)  # wrong count: no photos rather than guessed ones
    for scene, query in zip(scenes, suggested, strict=True):
        scene["photo_query"] = photo_query(scene, query)
    plan_beats(ctx.project_id, scenes, package.claims)
    return {"scenes.json": json.dumps(scenes, indent=2, ensure_ascii=False)}


# Shot planner (D-49): the big echo phrase under each sentence and the 1-2 full-screen text pops.
# Sonnet proposes; this validator keeps only what obeys the screen rules, else code decides.
POP_SECTIONS = {"Relevance", "Example", "Takeaway", "Context", "Build", "Recap"}
MAX_ECHO_WORDS, MAX_POP_WORDS, MAX_POPS = 4, 9, 2


def plan_beats(project_id: str, scenes: list[dict[str, Any]], claims: list[Claim]) -> None:
    """Sets scene["sentences"], scene["echo"] (one phrase per sentence) and, on 1-2 scenes,
    scene["pop"] = {"sentence", "text", "punch"}."""
    from app.adapters import prompts
    from app.nodes.rendering import sentences

    flat: list[tuple[dict[str, Any], int, str]] = []
    for scene in scenes:
        scene["sentences"] = sentences([scene["text"]])
        flat += [(scene, i, s) for i, s in enumerate(scene["sentences"])]
    proposed: dict[str, Any] = {}
    chat = llm.planner_chat(project_id)
    if chat is not None and flat:
        try:
            listed = [(scene["section"], text) for scene, _, text in flat]
            proposed = llm.ShotPlan.model_validate(
                chat.json(*prompts.shot_plan(listed), schema=llm.ShotPlan)).model_dump()
        except costs.BudgetExceeded:
            raise
        except Exception as error:  # the deterministic plan stands in
            log.warning("shot planner failed", reason=str(error))
        finally:
            costs.record_usage(project_id, "storyboarding", chat.calls)
    echoes = proposed.get("echoes", [])
    for n, (scene, _, text) in enumerate(flat):
        given = echoes[n] if n < len(echoes) else ""
        scene.setdefault("echo", []).append(
            given if valid_phrase(given, text, claims, MAX_ECHO_WORDS) else echo_words(text))
    pops = [p for p in proposed.get("pops", [])
            if 0 <= p["index"] < len(flat) and valid_pop(p, flat[p["index"]], claims)]
    if not pops:
        pops = default_pops(flat)
    for pop in pops[:MAX_POPS]:
        scene, index, _ = flat[pop["index"]]
        scene.setdefault("pop", {"sentence": index, "text": pop["text"], "punch": pop["punch"]})


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'.-]*[a-z0-9]|[a-z0-9]", text.lower())


def valid_phrase(phrase: str, sentence: str, claims: list[Claim], most: int) -> bool:
    """On-screen words (D-29): said in this sentence, few enough, and clean of claim words."""
    words = _words(phrase)
    return (0 < len(words) <= most and set(words) <= set(_words(sentence))
            and not script_checks.packaging_problems([phrase], claims))


def valid_pop(pop: dict[str, Any], beat: tuple[dict[str, Any], int, str],
              claims: list[Claim]) -> bool:
    scene, _, sentence = beat
    punch = [w.lower() for w in pop.get("punch", [])]
    return (scene["section"] in POP_SECTIONS and scene["visual_type"] != "end_card"
            and valid_phrase(pop.get("text", ""), sentence, claims, MAX_POP_WORDS)
            and 1 <= len(punch) <= 2 and set(punch) <= set(_words(pop["text"])))


def echo_words(sentence: str) -> str:
    """Deterministic echo: the sentence's (up to) three longest content words, in order."""
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", sentence)
             if len(w) > 3 and w.lower() not in script_checks.FILLER]
    keep = set(sorted(words, key=len, reverse=True)[:3])
    return " ".join(w for w in words if w in keep)[:60] or sentence.split()[0]


def default_pops(flat: list[tuple[dict[str, Any], int, str]]) -> list[dict[str, Any]]:
    """Deterministic pop: the first short body sentence (else a body sentence's first clause)
    as a full-screen statement, its longest word in serif italics."""
    for clause in (False, True):
        for n, (scene, _, text) in enumerate(flat):
            if scene["section"] not in POP_SECTIONS or scene["visual_type"] == "end_card":
                continue
            shown = re.split(r"[,:;]", text)[0].strip() if clause else text
            words = shown.split()
            content = [w.strip(".,!?\"'") for w in words
                       if w.strip(".,!?\"'").lower() not in script_checks.FILLER]
            if 2 <= len(words) <= MAX_POP_WORDS and content:
                return [{"index": n, "text": shown, "punch": [max(content, key=len)]}]
    return []


def photo_query(scene: dict[str, Any], suggested: str) -> str | None:
    """The scene's photo search: the model's literal phrase cleaned of anything the filters
    forbid. "none", no phrase, a diagram card or the end card: no photo (D-40)."""
    if scene["visual_type"] in DIAGRAMS:
        return None
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]+", suggested)
             if not stock.EXCLUDED.search(w)][:6]
    if not words or " ".join(words).lower() == "none":
        return None
    return " ".join(words).lower()


def visual_problems(script: str, claims: list[Claim]) -> list[str]:
    return [f"visual {s['on_screen']!r} gives the {s['visual_type']} template no "
            f"{REQUIRED[s['visual_type']]}; use the beat syntax from the rules"
            for s in parse(script, claims)
            if s["visual_type"] in REQUIRED and not s["props"].get(REQUIRED[s["visual_type"]])]


def parse(script: str, approved: list[Claim]) -> list[dict[str, Any]]:
    claims = {c.id: c for c in approved}
    scenes: list[dict[str, Any]] = []
    section = ""
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("[ON SCREEN"):
            beat = line.removeprefix("[ON SCREEN:").removesuffix("]").strip()
            scenes.append({"id": f"S{len(scenes) + 1}", "section": section, "on_screen": beat,
                           "visual_type": visual_type(beat), "text": "", "asset": None})
        elif line and scenes:
            scenes[-1]["text"] = f"{scenes[-1]['text']} {line}".strip()
    for scene in scenes:
        scene["props"] = props(scene, claims)
        words = script_checks.spoken_words([scene["text"]])
        scene["duration"] = round(words / script_checks.WORDS_PER_SECOND, 2)  # estimate at 150 wpm
    return scenes


def visual_type(beat: str) -> str:
    lowered = QUOTED.sub("", beat).lower()  # on-screen words never pick the template
    return next((kind for key, kind in VISUAL_TYPES if key in lowered), "title")


def props(scene: dict[str, Any], claims: dict[str, Claim]) -> dict[str, str | list[str]]:
    """Template fields, taken only from the beat and the approved claims it cites. A definition
    card shows the claim's approved wording; a quote card the source's verified quote."""
    beat, kind = scene["on_screen"], scene["visual_type"]
    quoted = QUOTED.findall(beat)
    source = re.search(r"source:\s*([^,\]]+)", beat, re.IGNORECASE)
    cited = [claims[f"C{n}"] for n in script_checks.MARKER.findall(scene["text"])
             if f"C{n}" in claims]
    fields: dict[str, str | list[str]] = {
        "headline": quoted[0] if quoted else "",
        "source": source.group(1).strip() if source else ""}
    if kind in ("definition_card", "quote_card") and cited:
        quote = kind == "quote_card"
        fields |= {"label": "QUOTE" if quote else "DEFINITION",
                   "definition": f"“{cited[0].quote}”" if quote else cited[0].claim,
                   "source_title": cited[0].title, "source_url": cited[0].url,
                   "quote": cited[0].quote}  # highlighted on the source-page capture (D-37)
    elif kind == "comparison":
        fields |= {"left": quoted[0] if quoted else "",
                   "right": quoted[1] if len(quoted) > 1 else "",
                   "between": "?" if "question mark" in beat.lower() else "vs"}
    elif kind == "chat_bubble":
        fields["message"] = quoted[0] if quoted else ""
    elif kind == "flow" and ":" in beat:  # 'illustrative flow, labelled "example": search, read'
        fields |= {"label": quoted[0] if quoted else "",
                   "steps": [s.strip() for s in beat.rsplit(":", 1)[1].split(",") if s.strip()]}
    elif kind == "flow" and len(quoted) >= 2:  # 'flow - "Question" to "Search" to "Answer"'
        fields |= {"label": "", "steps": quoted}
    elif kind == "checklist":
        fields["items"] = quoted
    elif kind == "end_card":
        fields["url"] = next((q for q in quoted if "." in q), "")
    return fields
