"""storyboarding: each `[ON SCREEN: ...]` beat + the narration under it becomes one scene (§4).

The script is parsed deterministically; template text comes only from the script and the approved
claim ledger. Each scene also gets a photo search phrase (D-34): suggested by the LLM in
production, built from the scene's own words in code in prototype mode or when the model's answer
doesn't fit. The reviewer approves the photos themselves at qa_review.
"""

import json
import re
from typing import Any

from app.adapters import llm, stock
from app.core import costs
from app.core.contracts import Claim, ContentPackage
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
        suggested = [""] * len(scenes)  # wrong count: phrases from the scenes' words instead
    for scene, query in zip(scenes, suggested, strict=True):
        scene["photo_query"] = photo_query(scene, query)
    return {"scenes.json": json.dumps(scenes, indent=2, ensure_ascii=False)}


def photo_query(scene: dict[str, Any], suggested: str) -> str | None:
    """The scene's photo search: the model's phrase cleaned of anything the filters forbid, else
    the scene's own words. The end card has no photo."""
    if scene["visual_type"] == "end_card":
        return None
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]+", suggested)
             if not stock.EXCLUDED.search(w)][:6]
    if words and " ".join(words).lower() != "none":
        return " ".join(words).lower()
    beat = QUOTED.findall(scene["on_screen"])
    return stock.keywords(" ".join(beat) + " " + scene["text"]) or None


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
