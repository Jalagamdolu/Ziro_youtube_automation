"""The planner: one list, one row per video through its whole life (D-64).

Planned → (being made, your reviews) → Ready → Scheduled → Published, in plain words. A row is a
planner topic, the video run it became, or both; a run made from New video (or before the planner
existed) is a row too. Ready videos without a slot are pinned at the top; the rest follow by
publish time. Publishing needs the final approval: no final approval, no scheduling (D-06).
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from starlette.datastructures import UploadFile

from app.adapters import storage
from app.core import config, db
from app.core.models import Artifact, Cost, Job, Project, Publishing, Topic
from app.graph.stages import REJECT_TARGETS
from app.jobs import scheduler
from app.ui import plain
from app.ui.routes import templates

router = APIRouter()
GROUPS = ["slot", "upcoming", "unscheduled", "published", "closed"]  # display order


def zone() -> timezone:
    offset = config.load()["planner"]["utc_offset"]  # "+05:30"
    delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
    return timezone(-delta if offset.startswith("-") else delta)


def shown(moment: datetime) -> str:
    return moment.astimezone(zone()).strftime("%a %d %b, %H:%M") + " IST"


def local_input(moment: datetime | None) -> str:
    """A datetime-local value in IST."""
    return moment.astimezone(zone()).strftime("%Y-%m-%dT%H:%M") if moment else ""


def parse_time(value: str) -> datetime | None:
    return datetime.fromisoformat(value).replace(tzinfo=zone()).astimezone(UTC) if value else None


def until(moment: datetime, now: datetime) -> str:
    """The countdown beside a scheduled time: in 3 days / in 5 h / in 12 min."""
    left = moment - now
    if left >= timedelta(hours=36):
        return f"in {round(left / timedelta(days=1))} days"
    if left >= timedelta(minutes=90):
        return f"in {round(left / timedelta(hours=1))} h"
    return f"in {max(1, round(left / timedelta(minutes=1)))} min"


def confirmation(receipt: dict[str, Any] | None) -> dict[str, str] | None:
    """Published only once confirmed, never on send alone (D-66). Mock: the receipt was written.
    Real YouTube later: the receipt carries `confirmed_at` and `watch_url` only after a read-back
    shows the video live. Anything else is still publishing."""
    if receipt is None:
        return None
    if receipt.get("mocked"):
        return {"label": "Published (mock)", "at": receipt.get("published_at", "")}
    if receipt.get("confirmed_at") and receipt.get("watch_url"):
        return {"label": "Live on YouTube", "at": receipt["confirmed_at"],
                "watch": receipt["watch_url"]}
    return None


def state(topic: Topic | None, project: Project | None, approved: datetime | None,
          now: datetime, confirmed: dict[str, str] | None = None) -> tuple[str, str, str]:
    """(chip text, chip class, group) for one video: one chip, one state (D-66). A missed slot
    and a failure are said loudly in red."""
    when = topic.publish_at if topic else None
    lead = timedelta(hours=config.load()["planner"]["start_hours_before"])
    if project is None:
        assert topic is not None
        if topic.status == "cancelled":
            return "Cancelled", "", "closed"
        if when is None:
            return "Planned", "", "unscheduled"
        return f"Planned · starts {shown(when - lead)}", "", "upcoming"
    status = project.status
    if status == "done" and confirmed:
        return confirmed["label"], "ok", "published"
    if status in ("done", *PUBLISHING) or (topic is not None and topic.status == scheduler.FIRING
                                         and status == scheduler.WAITING):
        return "Publishing…", "sched", "upcoming"
    if status in ("failed", "cancelled"):
        return ("Failed", "bad", "closed") if status == "failed" else ("Cancelled", "", "closed")
    if status == scheduler.WAITING:
        if when is None:
            return "Ready · needs a slot", "ready", "slot"
        if approved is not None and approved > when:
            return "Missed · needs a new time", "bad", "slot"
        if when > now:
            return f"Scheduled · {shown(when)} · {until(when, now)}", "sched", "upcoming"
        return "Publishing…", "sched", "upcoming"
    review = status in plain.GATES
    if when is not None and now >= when:
        return ("Missed · waiting for your review" if review else "Missed · still being made",
                "bad", "upcoming")
    return (("Needs your review", "warn") if review else ("Being made", "info")) + (
        "upcoming" if when else "unscheduled",)


PUBLISHING = ("mock_published", "metrics_stub")  # sent, receipt not yet confirmed
FILES = ("thumbnail.png", "publish_receipt.json", "qa_report.json")


def _receipt(files: dict[tuple[str, str], str], project: Project | None,
             published: dict[str, datetime]) -> dict[str, Any] | None:
    key = files.get((project.id, "publish_receipt.json")) if project else None
    if project is None or key is None:
        return None
    receipt: dict[str, Any] = json.loads(storage.get().read(key))
    if project.id in published:
        receipt.setdefault("published_at", shown(published[project.id]))
    return receipt


def _reason(job: Job | None) -> str:
    """Why a run failed, in plain words: the step and the first line of the error."""
    if job is None:
        return "It stopped without a recorded reason. Retry, or open it for details."
    step = plain.STATUS.get(job.stage, job.stage.replace("_", " ")).rstrip("…")
    message = (job.error_message or job.error_code or "unknown error").splitlines()[0][:160]
    return f"{step}: {message}"


def actions(row: dict[str, Any], submitted: str | None) -> str:
    """The one set of buttons this state offers (D-66)."""
    project, topic, chip = row["project"], row["topic"], row["chip"]
    if project is None:
        return "make" if topic is not None and topic.status == "planned" else ""
    if submitted == f"{project.id}:{project.status}":
        return "deciding"  # the decision is in; the worker has not moved on yet
    if project.status in plain.GATES:
        return "review"
    if project.status == "failed":
        return "retry"
    if project.status == scheduler.WAITING and chip != "Publishing…":
        return "schedule"
    return ""


def _seconds(files: dict[tuple[str, str], str], project: Project | None) -> float | None:
    """A finished video's real length, from its QA report (Ready, Scheduled, Published)."""
    if project is None or project.status not in (scheduler.WAITING, "done", *PUBLISHING):
        return None
    key = files.get((project.id, "qa_report.json"))
    if key is None:
        return None
    seconds = json.loads(storage.get().read(key)).get("duration_s")
    return float(seconds) if seconds is not None else None


def rows(submitted: str | None = None) -> list[dict[str, Any]]:
    """Every video, grouped and sorted for the list (D-64), each with its one chip and its
    actions (D-66). `submitted` is `project_id:gate` of a decision just sent from the list."""
    now = datetime.now(UTC)
    with db.session() as s:
        topics = s.scalars(select(Topic)).all()
        projects = {p.id: p for p in s.scalars(select(Project)).all()}
        files = {(a.project_id, a.type): a.storage_path for a in s.scalars(
            select(Artifact).where(Artifact.type.in_(FILES), Artifact.stale.is_(False))
            .order_by(Artifact.version))}
        spent = dict(s.execute(select(Cost.project_id, func.sum(Cost.amount))
                               .group_by(Cost.project_id)).all())
        approved = {p: scheduler.final_approved_at(s, p) for p, project in projects.items()
                    if project.status == scheduler.WAITING}
        published = {p.project_id: p.created_at for p in s.scalars(select(Publishing))}
        failures = {j.project_id: j for j in s.scalars(
            select(Job).where(Job.status == "failed").order_by(Job.id))}
    linked = {t.project_id for t in topics if t.project_id}
    pairs: list[tuple[Topic | None, Project | None]] = [
        (t, projects.get(t.project_id or "")) for t in topics]
    pairs += [(None, p) for p in projects.values() if p.id not in linked]
    found = []
    for topic, project in pairs:
        receipt = _receipt(files, project, published)
        confirmed = confirmation(receipt)
        chip, tone, group = state(topic, project, approved.get(project.id) if project else None,
                                 now, confirmed)
        when = topic.publish_at if topic else None
        created = project.created_at if project else topic.created_at if topic else now
        found.append({
            "topic": topic, "project": project, "chip": chip, "tone": tone, "group": group,
            "title": topic.topic if topic else project.topic if project else "",
            "when": when, "when_shown": shown(when) if when else "",
            "when_input": local_input(when), "created": created,
            "thumb": files.get((project.id, "thumbnail.png")) if project else None,
            "receipt": files.get((project.id, "publish_receipt.json")) if confirmed and project
            else None, "confirmed": confirmed,
            "reason": _reason(failures.get(project.id)) if project and project.status == "failed"
            else "",
            "targets": REJECT_TARGETS.get(project.status, []) if project else [],
            "seconds": _seconds(files, project),
            "cost": plain.rupees(spent.get(project.id) or 0) if project else "",
            "upload": bool(topic and topic.kind == "upload"),
            "doing": plain.status(project.status) if project else ""})
        found[-1]["do"] = actions(found[-1], submitted)
        if found[-1]["do"] == "deciding":
            found[-1].update(chip="Working on your decision…", tone="info")

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        newest_first = -row["created"].timestamp()
        moment = row["when"].timestamp() if row["when"] else 0
        order = {"upcoming": moment, "published": -moment or newest_first}
        return GROUPS.index(row["group"]), order.get(row["group"], newest_first)

    return sorted(found, key=key)


@router.get("/planner", response_class=HTMLResponse)
def planner(request: Request, error: str | None = None,
            submitted: str | None = None) -> HTMLResponse:
    listed = rows(submitted)
    return templates.TemplateResponse(request, "planner.html", {
        "rows": listed, "error": error, "groups": GROUPS,
        "counts": {g: sum(1 for r in listed if r["group"] == g) for g in GROUPS},
        "lead": config.load()["planner"]["start_hours_before"],
        "min_time": local_input(datetime.now(UTC) + timedelta(minutes=5))})


@router.post("/planner")
async def add_topic(request: Request) -> RedirectResponse:
    """Add a row: topic, guidelines, format, duration and an optional publish time."""
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    try:
        topic = Topic(topic=form["topic"], format=form.get("format", "short"), keywords=[],
                      guidelines=form.get("guidelines", ""),
                      publish_at=parse_time(form.get("publish_at", "")), status="planned",
                      target_seconds=int(form["target_seconds"]) if form.get("target_seconds")
                      else None, created_by=request.state.user["name"])
    except (KeyError, ValueError) as error:
        return RedirectResponse(f"/planner?error=could not read the topic: {error}",
                                status_code=303)
    if not topic.topic:
        return RedirectResponse("/planner?error=a topic is required", status_code=303)
    with db.session() as s, s.begin():
        s.add(topic)
    return RedirectResponse("/planner", status_code=303)


@router.get("/planner/{topic_id}", response_class=HTMLResponse, response_model=None)
def planned(request: Request, topic_id: int) -> HTMLResponse | RedirectResponse:
    """A planned row's own page; once its video exists, that video's page is the row's page."""
    with db.session() as s:
        topic = s.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(404, "no such row")
    if topic.project_id:
        return RedirectResponse(f"/ui/projects/{topic.project_id}", status_code=303)
    lead = timedelta(hours=config.load()["planner"]["start_hours_before"])
    chip, tone, _ = state(topic, None, None, datetime.now(UTC))
    return templates.TemplateResponse(request, "planned.html", {
        "topic": topic, "chip": chip, "tone": tone,
        "when": shown(topic.publish_at) if topic.publish_at else None,
        "starts": shown(topic.publish_at - lead) if topic.publish_at else None})


@router.post("/planner/{topic_id}/run")
def run_now(request: Request, topic_id: int) -> RedirectResponse:
    """Make now: start a planned row's video at once, through the scheduler's own path."""
    try:
        project_id = scheduler.start_topic(topic_id, request.state.user["name"])
    except HTTPException as error:
        return RedirectResponse(f"/planner?error={error.detail}", status_code=303)
    if project_id is None:
        return RedirectResponse("/planner?error=that topic has already started", status_code=303)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


@router.post("/planner/{topic_id}/cancel")
def cancel_topic(request: Request, topic_id: int) -> RedirectResponse:
    with db.session() as s, s.begin():
        topic = s.get(Topic, topic_id)
        if topic and topic.status == "planned":
            topic.status = "cancelled"
    return RedirectResponse("/planner", status_code=303)


@router.post("/videos/{project_id}/schedule")
async def set_slot(request: Request, project_id: str) -> RedirectResponse:
    """Schedule, reschedule or (empty time / Unschedule) clear a Ready video's slot."""
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    back = form.get("back", "/planner") if form.get("back", "").startswith("/") else "/planner"
    try:
        when = None if form.get("action") == "unschedule" else parse_time(form.get("publish_at",
                                                                                     ""))
        scheduler.schedule(project_id, when, request.state.user["name"])
    except ValueError as error:
        sep = "&" if "?" in back else "?"
        return RedirectResponse(f"{back}{sep}error={error}", status_code=303)
    return RedirectResponse(back, status_code=303)


@router.post("/planner/upload")
async def upload(request: Request) -> RedirectResponse:
    """Add an external MP4 (e.g. sir's recording) as a Ready row, approved by hand (D-64)."""
    form = await request.form()
    video, title = form.get("video"), str(form.get("title", "")).strip()
    if not isinstance(video, UploadFile) or not title:
        return RedirectResponse("/planner?error=a title and an MP4 file are needed",
                                status_code=303)
    if form.get("approve") != "yes":
        return RedirectResponse("/planner?error=tick the approval box: only an approved video "
                                "can be scheduled", status_code=303)
    try:
        project_id = scheduler.upload(title, await video.read(), video.filename or "video.mp4",
                                      request.state.user["name"])
    except ValueError as error:
        return RedirectResponse(f"/planner?error={error}", status_code=303)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


def schedule(project_id: str, status: str) -> dict[str, Any] | None:
    """For the detail page: the video's slot and what it means now."""
    with db.session() as s:
        topic = s.scalars(select(Topic).where(Topic.project_id == project_id)).first()
        approved = scheduler.final_approved_at(s, project_id)
    when = topic.publish_at if topic else None
    now = datetime.now(UTC)
    if when is None and status != scheduler.WAITING:
        return None
    missed = when is not None and status != "done" and (
        now >= when if status != scheduler.WAITING else approved is not None and approved > when)
    return {"when": shown(when) if when else None, "when_input": local_input(when),
            "missed": missed, "ready": status == scheduler.WAITING, "upload": bool(
                topic and topic.kind == "upload"),
            "min_time": local_input(now + timedelta(minutes=5))}
