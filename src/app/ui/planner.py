"""The planner: one list, one row per video through its whole life (D-64).

Planned → (being made, your reviews) → Ready → Scheduled → Published, in plain words. A row is a
planner topic, the video run it became, or both; a run made from New video (or before the planner
existed) is a row too. Ready videos without a slot are pinned at the top; the rest follow by
publish time. Publishing needs the final approval: no final approval, no scheduling (D-06).
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.core import config, db
from app.core.models import Artifact, Project, Topic
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


def state(topic: Topic | None, project: Project | None, approved: datetime | None,
          now: datetime) -> tuple[str, str, str]:
    """(chip text, chip class, group) for one video. A missed slot is said loudly in red."""
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
    if status == "done":
        return "Published", "ok", "published"
    if status in ("failed", "cancelled"):
        return ("Stopped", "bad", "closed") if status == "failed" else ("Cancelled", "", "closed")
    if status == scheduler.WAITING:
        if when is None:
            return "Ready · needs a slot", "ready", "slot"
        if approved is not None and approved > when:
            return "Missed · needs a new time", "bad", "slot"
        if when > now:
            return f"Scheduled · {shown(when)}", "sched", "upcoming"
        return "Publishing…", "sched", "upcoming"
    review = status in plain.GATES
    if when is not None and now >= when:
        return ("Missed · waiting for your review" if review else "Missed · still being made",
                "bad", "upcoming")
    return (("Needs your review", "warn") if review else ("Being made", "info")) + (
        "upcoming" if when else "unscheduled",)


def rows() -> list[dict[str, Any]]:
    """Every video, grouped and sorted for the list (D-64)."""
    now = datetime.now(UTC)
    with db.session() as s:
        topics = s.scalars(select(Topic)).all()
        projects = {p.id: p for p in s.scalars(select(Project)).all()}
        thumbs = {a.project_id: a.storage_path for a in s.scalars(
            select(Artifact).where(Artifact.type == "thumbnail.png", Artifact.stale.is_(False))
            .order_by(Artifact.version))}
        approved = {p: scheduler.final_approved_at(s, p) for p, project in projects.items()
                    if project.status == scheduler.WAITING}
    linked = {t.project_id for t in topics if t.project_id}
    pairs: list[tuple[Topic | None, Project | None]] = [
        (t, projects.get(t.project_id or "")) for t in topics]
    pairs += [(None, p) for p in projects.values() if p.id not in linked]
    found = []
    for topic, project in pairs:
        chip, tone, group = state(topic, project, approved.get(project.id) if project else None,
                                 now)
        when = topic.publish_at if topic else None
        created = project.created_at if project else topic.created_at if topic else now
        found.append({
            "topic": topic, "project": project, "chip": chip, "tone": tone, "group": group,
            "title": topic.topic if topic else project.topic if project else "",
            "when": when, "when_shown": shown(when) if when else "",
            "when_input": local_input(when), "created": created,
            "thumb": thumbs.get(project.id) if project else None,
            "upload": bool(topic and topic.kind == "upload"),
            "doing": plain.status(project.status) if project else ""})

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        newest_first = -row["created"].timestamp()
        moment = row["when"].timestamp() if row["when"] else 0
        order = {"upcoming": moment, "published": -moment or newest_first}
        return GROUPS.index(row["group"]), order.get(row["group"], newest_first)

    return sorted(found, key=key)


@router.get("/planner", response_class=HTMLResponse)
def planner(request: Request, error: str | None = None) -> HTMLResponse:
    listed = rows()
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
