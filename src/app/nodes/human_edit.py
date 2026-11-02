"""Human-edit bridge: a reviewer edits a script package by hand and it goes through scripting's
normal checks, nothing skipped (D-30).

The editable file is plain text: `=== SECTION ===` headers, and `!!` lines that are notes (which
rule a line breaks and an example fix); notes are ignored when the file is read back. Scripting
uses the file instead of the LLM when it exists at `<project_id>/scripting/human_draft.md`.
"""

import re

from app.core.contracts import Chapter, HookDraft, PackageDraft

KEY = "{}/scripting/human_draft.md"
HEADER = re.compile(r"^=== (.+) ===$", re.MULTILINE)
# Problem text -> example fix shown under the line that breaks it.
FIXES = [
    ("claims '", "say what it does, not how much better it makes things, e.g. "
                 "\"How RAG Connects Models To Data\""),
    ("on-screen", "show only words the narration says, or say them in the narration"),
    ("runtime", "add or cut spoken words in the Example section (112-188 in total)"),
    ("Hook section", "make the Hook line exactly one of the two top-scoring hooks"),
    ("relevance must land", "keep Hook + Relevance to 25 spoken words or fewer"),
    ("unsourced figure", "cite the claim it comes from, e.g. [C2], or drop the figure"),
    ("banned claim", "remove it; the brief forbids it unless supplied as an approved fact"),
    ("template no", "use the beat syntax, e.g. [ON SCREEN: flow - \"Ask\" to \"Fetch\"]"),
]


def render(draft: PackageDraft, problems: list[str], editor: str) -> str:
    body = "\n".join([
        "=== EDITED BY ===", editor,
        "=== SCRIPT ===", draft.script.strip(),
        "=== HOOKS ===", *(f"{h.text} | {h.explanation}" for h in draft.hooks),
        "=== TITLES ===", *draft.titles,
        "=== THUMBNAIL ===", draft.thumbnail_text,
        "=== DESCRIPTION ===", draft.description.strip(),
        "=== TAGS ===", *draft.tags,
        "=== TARGET QUERIES ===", *draft.target_queries,
        "=== CHAPTERS ===", *(f"{c.start_seconds} | {c.title}" for c in draft.chapters),
    ])
    lines = body.split("\n")
    unplaced = []
    for problem in problems:
        note = f"!! RULE: {problem}\n!! FIX: {_fix(problem)}"
        quoted = re.findall(r"'([^']{3,})'", problem)
        at = next((i for q in reversed(quoted) for i, line in enumerate(lines)
                   if q[:40].lower() in line.lower() and not line.startswith("!!")), None)
        if at is None:
            unplaced.append(note)
        else:
            lines[at] += "\n" + note
    guide = ["!! Lines starting with !! are notes and are ignored. Edit anything else, keep the",
             "!! === headers ===, save, and say \"edited\". Every check runs on your version."]
    return "\n".join(guide + unplaced + lines) + "\n"


def parse(text: str) -> tuple[PackageDraft, str]:
    """(draft, editor) from an edited file; raises ValueError naming what is malformed."""
    kept = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("!!"))
    parts = HEADER.split(kept)
    sections = {name.strip(): body.strip() for name, body in zip(parts[1::2], parts[2::2],
                                                                   strict=True)}

    def lines(name: str) -> list[str]:
        if name not in sections:
            raise ValueError(f"missing section === {name} ===")
        return [line.strip() for line in sections[name].splitlines() if line.strip()]

    hooks = [HookDraft(text=t.strip(), explanation=e.strip())
             for t, _, e in (line.partition("|") for line in lines("HOOKS"))]
    chapters = [Chapter(start_seconds=int(s), title=t.strip())
                for s, _, t in (line.partition("|") for line in lines("CHAPTERS"))]
    draft = PackageDraft(
        script=sections["SCRIPT"] + "\n", hooks=hooks, titles=lines("TITLES"),
        thumbnail_text=" ".join(lines("THUMBNAIL")), description=sections.get("DESCRIPTION", ""),
        tags=lines("TAGS"), target_queries=lines("TARGET QUERIES"), chapters=chapters)
    return draft, " ".join(lines("EDITED BY"))


def _fix(problem: str) -> str:
    return next((fix for key, fix in FIXES if key in problem), "see the rule above")
