"""storyboarding: each `[ON SCREEN: ...]` beat + the narration under it becomes one scene (§4).

Prototype mode parses the approved script deterministically (an LLM storyboard is a production
option). Template text comes only from the script and the approved claim ledger.
"""

import json
import re
from typing import Any

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


def storyboarding(ctx: StageContext) -> Outputs:
    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    claims = {c.id: c for c in package.claims}
    scenes: list[dict[str, Any]] = []
    section = ""
    for line in package.script.splitlines():
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
    return {"scenes.json": json.dumps(scenes, indent=2, ensure_ascii=False)}


def visual_type(beat: str) -> str:
    lowered = beat.lower()
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
                   "source_title": cited[0].title, "source_url": cited[0].url}
    elif kind == "comparison":
        fields |= {"left": quoted[0] if quoted else "",
                   "right": quoted[1] if len(quoted) > 1 else "",
                   "between": "?" if "question mark" in beat.lower() else "vs"}
    elif kind == "chat_bubble":
        fields["message"] = quoted[0] if quoted else ""
    elif kind == "flow" and ":" in beat:  # 'illustrative flow, labelled "example": search, read'
        fields |= {"label": quoted[0] if quoted else "",
                   "steps": [s.strip() for s in beat.rsplit(":", 1)[1].split(",") if s.strip()]}
    elif kind == "checklist":
        fields["items"] = quoted
    elif kind == "end_card":
        fields["url"] = next((q for q in quoted if "." in q), "")
    return fields
