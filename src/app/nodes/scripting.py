"""scripting: hooks + script + package in one stage (§4), from approved claims only.

The draft is checked deterministically; on failure the LLM gets the problems as revision notes,
at most MAX_REVISIONS times, then the stage fails (FatalError, never retried).
"""

import json
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.adapters import llm, prompts
from app.core import config, costs, db
from app.core.contracts import Brief, Claim, ContentPackage, Hook, PackageDraft
from app.core.errors import FatalError
from app.core.log import log
from app.core.models import Approval, Artifact
from app.nodes import human_edit, script_checks, skills
from app.nodes.context import Outputs, StageContext
from app.nodes.storyboarding import visual_problems

MAX_REVISIONS = 2
LENGTH = re.compile(r"\bcut about \d+ spoken words")  # a length problem from the checker


class ChecksFailed(FatalError):
    """The last draft still broke checks after every allowed revision."""

    def __init__(self, message: str, draft: PackageDraft, problems: list[str]) -> None:
        super().__init__(message)
        self.draft, self.problems = draft, problems


def scripting(ctx: StageContext) -> Outputs:
    brief = Brief.model_validate(ctx.read_json("draft", "brief.json"))
    claims = approved_claims(ctx.project_id, ctx.read_json("researching", "claims.json"))
    trail: Outputs = {}
    edited = human_edit.KEY.format(ctx.project_id)
    editor = "Dolender"
    try:
        if ctx.storage.exists(edited):  # the reviewer's hand edit replaces the model, not checks
            text = ctx.storage.read(edited).decode("utf-8")
            # Used once, pass or fail: a failed edit survives as the flagged last draft, and
            # a later retry or reject goes back to the model instead of re-running this text.
            ctx.storage.delete(edited)
            try:
                package_draft, editor = human_edit.parse(text)
            except ValueError as error:
                raise FatalError(f"human-edited draft is malformed: {error}") from error
            draft, hooks, titles = _write(lambda _: package_draft, brief, claims, None,
                                          revisions=0)
            log.info("script human-edited", editor=editor)
            trail = {"human_draft.txt": text,
                     "human_edit.json": json.dumps({"edited_by": editor, "source": edited})}
        else:
            writer = llm.get("scripting", ctx.project_id)
            notes = ctx.notes
            if notes and (previous := _previous_script(ctx)):  # a reject edits the reviewed one
                notes += f"\nThe reviewed script, to edit rather than rewrite:\n{previous}"
            try:
                revisions = MAX_REVISIONS if config.load()["mode"] == "production" else 0
                draft, hooks, titles = _write(
                    lambda n: writer.write_package(brief, claims, n), brief, claims, notes,
                    revisions)
            finally:
                costs.record_usage(ctx.project_id, "scripting", writer.calls)
    except ChecksFailed as failed:  # keep the last draft, flagged, for the hand-edit bridge
        ctx.storage.write(human_edit.LAST_FAILED.format(ctx.project_id),
                          human_edit.render(failed.draft, failed.problems, editor).encode())
        raise

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
        "support_flags.json": json.dumps(support_flags(ctx.project_id, draft.script, claims),
                                         indent=2, ensure_ascii=False),
    } | trail


def support_flags(project_id: str, script: str, claims: list[Claim]) -> dict[str, Any]:
    """Claude Haiku's support check (D-44): does a cited line say more than its quote? Flags for
    the reviewer only: it never approves and never blocks, so a failed check becomes a note.
    Only the budget cap (D-45) still stops the run."""
    chat = llm.support_chat(project_id)
    if chat is None:
        return {"status": "not run", "reason": "needs production mode and ANTHROPIC_API_KEY",
                "verdicts": []}
    cited = script_checks.cited_sentences(script)
    try:
        reply = chat.json(*prompts.support(cited, claims), schema=llm.SupportReport)
        verdicts = llm.SupportReport.model_validate(reply).verdicts
    except costs.BudgetExceeded:
        raise
    except Exception as error:  # flags only: whatever goes wrong, the script is not blocked
        log.warning("support check failed", reason=str(error))
        return {"status": "not run", "reason": str(error)[:300], "verdicts": []}
    finally:
        costs.record_usage(project_id, "scripting", chat.calls)
    return {"status": "ok", "model": chat.model,
            "verdicts": [v.model_dump() for v in verdicts]}


def _write(write: Callable[[str | None], PackageDraft], brief: Brief, claims: list[Claim],
           notes: str | None, revisions: int
           ) -> tuple[PackageDraft, list[dict[str, Any]], list[dict[str, Any]]]:
    reviewer = f"Reviewer notes: {notes}\n" if notes else ""
    for attempt in range(1 + revisions):
        draft = write(notes)
        hooks = skills.score_hooks([h.text for h in draft.hooks])
        titles = skills.lint_titles(draft.titles, draft.thumbnail_text)
        problems = _problems(draft, brief, claims, hooks, titles)
        log.info("draft checked", draft=attempt + 1, problems=problems, script=draft.script)
        if not problems:
            return draft, hooks, titles
        notes = revision_notes(reviewer, problems, draft.script)
    raise ChecksFailed(f"script failed checks after {revisions} revisions: "
                       + "; ".join(problems), draft, problems)


def revision_notes(reviewer: str, problems: list[str], script: str) -> str:
    """What the model gets back: its own draft and exactly what to change. A length cut leads,
    word for word as the checker counted it ("cut about 68 spoken words in the Example
    section"), so a revision actually shortens the script (D-71)."""
    lengths = [p for p in problems if LENGTH.search(p)]
    first = ("LENGTH FIRST — the script is too long: " + "; ".join(lengths)
             + ". Remove that many spoken words there; keep every [C#] claim and the CTA.\n"
             if lengths else "")
    return (f"{reviewer}{first}Fix: " + "; ".join(problems)
            + f"\nYour previous script, to revise rather than restart:\n{script}")


def _previous_script(ctx: StageContext) -> str | None:
    """The newest script.md this project's scripting stage wrote (stale or not)."""
    with db.session() as s:
        path = s.scalars(
            select(Artifact.storage_path)
            .where(Artifact.project_id == ctx.project_id, Artifact.stage == "scripting",
                   Artifact.type == "script.md")
            .order_by(Artifact.version.desc())
            .limit(1)
        ).first()
    return ctx.storage.read(path).decode("utf-8") if path else None


def approved_claims(project_id: str, researched: list[dict[str, Any]]) -> list[Claim]:
    """The researched claims, with removals/edits from a research_review approval (runs from
    before v2 had that gate; D-50)."""
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
    problems += visual_problems(draft.script, claims)
    problems += script_checks.on_screen_problems(draft.script, claims, brief.topic)
    problems += script_checks.mechanism_problems(draft.script, claims, brief.topic)
    problems += script_checks.uncited_problems(draft.script, brief)
    problems += script_checks.packaging_problems(
        [*draft.titles, draft.thumbnail_text, draft.description, *draft.tags], claims)
    if len({h.text.strip().lower() for h in draft.hooks}) != 5:
        problems.append("the five hooks must be distinct")
    opening = script_checks.hook_line(draft.script)
    if not any(h["hook"] in opening for h in hooks[:2]):
        top = " or ".join(repr(h["hook"]) for h in hooks[:2])
        problems.append(f"the Hook section must be exactly one of the two top-scoring hooks: {top}")
    if any(issue == "duplicate" for issue, _ in titles[0]["issues"]):
        problems.append("thumbnail text repeats the top title")
    return problems
