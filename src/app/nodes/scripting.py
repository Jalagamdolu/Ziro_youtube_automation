"""scripting: hooks + script + package in one stage (§4), from approved claims only.

The draft is checked deterministically; on failure the LLM gets the problems as revision notes,
at most MAX_REVISIONS times, then the stage fails (FatalError, never retried).
"""

import json
from typing import Any

from sqlalchemy import select

from app.adapters import llm
from app.core import db
from app.core.contracts import Brief, Claim, ContentPackage, Hook, PackageDraft
from app.core.errors import FatalError
from app.core.models import Approval
from app.nodes import script_checks, skills
from app.nodes.context import Outputs, StageContext

MAX_REVISIONS = 2


def scripting(ctx: StageContext) -> Outputs:
    brief = Brief.model_validate(ctx.read_json("draft", "brief.json"))
    claims = approved_claims(ctx.project_id, ctx.read_json("researching", "claims.json"))
    writer = llm.get()
    notes = ctx.notes
    for _ in range(1 + MAX_REVISIONS):
        draft = writer.write_package(brief, claims, notes)
        hooks = skills.score_hooks([h.text for h in draft.hooks])
        titles = skills.lint_titles(draft.titles, draft.thumbnail_text)
        problems = _problems(draft, brief, claims, hooks, titles)
        if not problems:
            break
        notes = "Fix: " + "; ".join(problems)
    else:
        raise FatalError(f"script failed checks after {MAX_REVISIONS} revisions: {notes}")

    explanations = {h.text: h.explanation for h in draft.hooks}
    package = ContentPackage(
        brief=brief,
        claims=claims,
        script=draft.script,
        hooks=[Hook(text=h["hook"], score=h["verdict"], formula=h["formula"],
                    explanation=explanations[h["hook"]]) for h in hooks],
        top_hooks=[h["hook"] for h in hooks[:2]],
        titles=draft.titles,
        top_titles=[t["title"] for t in titles[:3]],
        thumbnail_text=draft.thumbnail_text,
        description=draft.description,
        tags=draft.tags,
        target_queries=draft.target_queries,
        chapters=draft.chapters,
    )
    return {
        "script.md": draft.script,
        "content_package.json": package.model_dump_json(indent=2),
        "hook_scores.json": json.dumps(hooks, indent=2, ensure_ascii=False),
        "title_lint.json": json.dumps(titles, indent=2, ensure_ascii=False),
    }


def approved_claims(project_id: str, researched: list[dict[str, Any]]) -> list[Claim]:
    """Claims as the reviewer left them at research_review: removals dropped, edits applied."""
    with db.session() as s:
        approval = s.scalars(
            select(Approval)
            .where(Approval.project_id == project_id, Approval.stage == "research_review",
                   Approval.decision == "approve")
            .order_by(Approval.timestamp.desc())
            .limit(1)
        ).first()
    edits = (approval.claim_edits if approval else None) or {}
    removed = set(edits.get("removed", []))
    edited = edits.get("edited", {})
    claims = [Claim.model_validate(c) for c in researched if c["id"] not in removed]
    return [c.model_copy(update={"claim": edited[c.id]}) if c.id in edited else c for c in claims]


def _problems(draft: PackageDraft, brief: Brief, claims: list[Claim],
              hooks: list[dict[str, Any]], titles: list[dict[str, Any]]) -> list[str]:
    problems = script_checks.claim_problems(draft.script, claims)
    problems += script_checks.shape_problems(draft.script, brief)
    if len({h.text.strip().lower() for h in draft.hooks}) != 5:
        problems.append("the five hooks must be distinct")
    opening = script_checks.hook_line(draft.script)
    if not any(h["hook"] in opening for h in hooks[:2]):
        problems.append("the script must open with one of the two top-scoring hooks")
    if any(issue == "duplicate" for issue, _ in titles[0]["issues"]):
        problems.append("thumbnail text repeats the top title")
    return problems
