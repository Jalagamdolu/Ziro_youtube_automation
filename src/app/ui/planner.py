"""Every video's one status, its actions, and the Planner (D-64, D-66, D-69).

One status per video, in plain words: Writing script → Needs your review (script) → Generating →
Needs your review (video) → Ready → Scheduled → Publishing → Published, plus Failed (reason +
Retry) and Cancelled; a planner topic with no video yet is Planned. The Library shows every
video; the Planner is the calendar of what has a time (scheduled, publishing, published, failed
to publish, planned). Published only after confirmation: the mock receipt, or YouTube's read-back.
Publishing needs the final approval: no final approval, no scheduling (D-06). All times IST.
"""

import calendar
import json
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from starlette.datastructures import UploadFile

from app.adapters import publisher, storage
from app.core import config, db, metadata
from app.core.models import Artifact, Job, Project, Publishing, Topic
from app.jobs import scheduler
from app.ui import plain
from app.ui.routes import templates

router = APIRouter()
WRITING = ("draft", "researching", "scripting")
GENERATING = ("storyboarding", "rendering")
PUBLISHING = ("mock_published", "metrics_stub")  # sent, not yet confirmed
NEEDS_YOU = ("script_review", "qa_review")
# Library filters: key -> (label, the statuses it shows)
FILTERS = {"all": ("All", None), "needs": ("Needs you", {"review_script", "review_video"}),
           "ready": ("Ready", {"ready"}), "scheduled": ("Scheduled", {"scheduled"}),
           "published": ("Published", {"published"}), "failed": ("Failed", {"failed"}),
           "archived": ("Archived", None)}  # archived: hidden from every other view (D-73)


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


def confirmation(row: Publishing | None, receipt: bool) -> dict[str, str] | None:
    """Published only once confirmed, never on send alone (D-66, D-69). Mock: its receipt was
    written. YouTube: a read-back set confirmed_at (public, or released and kept private by an
    unaudited API project). Anything else is still publishing."""
    if row is None:
        return None
    if row.platform == "youtube-mock":
        return {"label": "Published (mock)", "at": shown(row.created_at),
                "video_id": row.provider_video_id} if receipt else None
    if row.confirmed_at is None:
        return None
    label = "Published" if row.privacy == "public" else "Published · private"
    return {"label": label, "at": shown(row.confirmed_at), "watch": row.watch_url or "",
            "video_id": row.provider_video_id}


def state(topic: Topic | None, project: Project | None, approved: datetime | None,
          now: datetime, row: Publishing | None = None,
          confirmed: dict[str, str] | None = None) -> tuple[str, str, str]:
    """(chip text, chip class, status key) for one video: one chip, one state."""
    when = topic.publish_at if topic else None
    if project is None:
        assert topic is not None
        if topic.status == "cancelled":
            return "Cancelled", "", "cancelled"
        lead = timedelta(hours=config.load()["planner"]["start_hours_before"])
        return ((f"Planned · starts {shown(when - lead)}", "", "planned") if when
                else ("Planned", "", "planned"))
    status = project.status
    if status == "done" and confirmed:
        return confirmed["label"], "ok", "published"
    on_youtube = row is not None and row.platform == "youtube" and row.privacy != "public"
    if status == "done" and row is not None and on_youtube:
        if row.scheduled_at is None:
            return "Ready · on YouTube, private", "ready", "ready"
        if row.scheduled_at > now:
            return (f"Scheduled · {shown(row.scheduled_at)} · {until(row.scheduled_at, now)}",
                    "sched", "scheduled")
    if status in ("done", *PUBLISHING) or (
            status == scheduler.WAITING and topic is not None and topic.status == scheduler.FIRING):
        return "Publishing…", "sched", "publishing"
    if status == "failed":
        return "Failed", "bad", "failed"
    if status == "cancelled":
        return "Cancelled", "", "cancelled"
    if status in (scheduler.WAITING, "approved"):
        if when is None:
            return "Ready", "ready", "ready"
        if approved is not None and approved > when:
            return "Ready · missed its slot, pick a new time", "bad", "ready_missed"
        if when > now:
            return f"Scheduled · {shown(when)} · {until(when, now)}", "sched", "scheduled"
        return "Publishing…", "sched", "publishing"
    missed = when is not None and now >= when
    if status in NEEDS_YOU:
        which = "script" if status == "script_review" else "video"
        chip = f"Needs your review ({which})" + (" · missed its slot" if missed else "")
        return chip, "bad" if missed else "warn", f"review_{which}"
    if status in GENERATING:
        return "Generating…", "bad" if missed else "info", "generating"
    return "Writing script…", "bad" if missed else "info", "writing"


FILES = ("thumbnail.png", "publish_receipt.json", "qa_report.json", "video.mp4")


def _seconds(files: dict[tuple[str, str], str], project: Project | None) -> float | None:
    """A finished video's real length, from its QA report."""
    key = files.get((project.id, "qa_report.json")) if project else None
    if key is None or project is None or project.status in (*WRITING, *GENERATING, *NEEDS_YOU):
        return None
    seconds = json.loads(storage.get().read(key)).get("duration_s")
    return float(seconds) if seconds is not None else None


def _reason(job: Job | None, asked: int | None = None) -> str:
    """Why a run failed, in plain words (D-71): length failures say what came out and what was
    asked; other script failures point at the flagged draft; anything else is the step and the
    first line of the error. The raw error stays in Technical details."""
    if job is None:
        return "It stopped without a recorded reason. Retry, or open it for details."
    message = job.error_message or job.error_code or "unknown error"
    plain_words = plain.failure(message, asked, config.load()["mode"])
    if plain_words:
        return plain_words
    step = plain.STATUS.get(job.stage, job.stage.replace("_", " ")).rstrip("…")
    return f"{step}: {message.splitlines()[0][:160]}"


def actions(key: str, project: Project | None, row: Publishing | None) -> list[str]:
    """The buttons this one state offers."""
    if project is None:
        return ["make"] if key == "planned" else []
    has_video = project.status not in (*WRITING, *GENERATING, "script_review", "failed")
    base = ["preview", "download"] if has_video and key != "review_video" else []
    if key in ("review_script", "review_video"):
        return ["review"]
    if key in ("writing", "generating"):
        return ["open"]
    if key == "failed":
        return ["retry"]
    editable = project.status in metadata.EDITABLE
    if key in ("ready", "ready_missed"):
        return [*base, *(["edit"] if editable else []), "publish_now", "schedule"]
    if key == "scheduled":
        return [*base, *(["edit"] if editable else []), "reschedule", "unschedule", "publish_now"]
    return base


def videos(saved: str | None = None, only: str | None = None) -> list[dict[str, Any]]:
    """Every video and planned topic with its one status and actions (`only`: one video)."""
    now = datetime.now(UTC)
    with db.session() as s:
        topics = s.scalars(select(Topic).where(Topic.project_id == only) if only
                           else select(Topic)).all()
        projects = {p.id: p for p in s.scalars(select(Project).where(Project.id == only) if only
                                               else select(Project)).all()}
        files = {(a.project_id, a.type): a.storage_path for a in s.scalars(
            select(Artifact).where(Artifact.type.in_(FILES), Artifact.stale.is_(False))
            .order_by(Artifact.version))}
        approved = {p: scheduler.final_approved_at(s, p) for p, project in projects.items()
                    if project.status in (scheduler.WAITING, "approved")}
        published = {r.project_id: r for r in s.scalars(select(Publishing))}
        failures = {j.project_id: j for j in s.scalars(
            select(Job).where(Job.status == "failed").order_by(Job.id))}
        metas = {p: metadata.current(s, p) for p in projects
                 if projects[p].status in metadata.EDITABLE}
    linked = {t.project_id for t in topics if t.project_id}
    pairs: list[tuple[Topic | None, Project | None]] = [
        (t, projects.get(t.project_id or "")) for t in topics]
    pairs += [(None, p) for p in projects.values() if p.id not in linked]
    found = []
    for topic, project in pairs:
        pid = project.id if project else None
        row = published.get(pid or "")
        confirmed = confirmation(row, (pid, "publish_receipt.json") in files)
        chip, tone, key = state(topic, project, approved.get(pid or ""), now, row, confirmed)
        when = (row.scheduled_at if row and row.scheduled_at else None) or (
            topic.publish_at if topic else None)
        if key == "published" and row is not None:
            when = row.confirmed_at or row.created_at
        if saved and pid == saved and key in ("review_video", "publishing", "writing"):
            chip, tone, key = "Saving to Library…", "info", "saving"
        found.append({
            "topic": topic, "project": project, "id": pid, "chip": chip, "tone": tone,
            "archived": bool(project and project.archived),
            "key": key, "busy": chip.endswith("…"),
            "title": metas[pid]["title"] if pid in metas else (
                project.topic if project else topic.topic if topic else ""),
            "meta": metas.get(pid or ""),
            "when": when, "when_shown": shown(when) if when else "",
            "when_input": local_input(when if key in ("scheduled", "ready_missed") else None),
            "created": (created := project.created_at if project else
                        topic.created_at if topic else now),
            "created_shown": created.astimezone(zone()).strftime("%d %b %Y"),
            "thumb": files.get((pid, "thumbnail.png")) if pid else None,
            "video": files.get((pid, "video.mp4")) if pid else None,
            "receipt": files.get((pid, "publish_receipt.json")) if confirmed and pid else None,
            "confirmed": confirmed, "seconds": _seconds(files, project),
            "upload": bool(topic and topic.kind == "upload"),
            "reason": _reason(failures.get(pid or ""), project.target_seconds if project
                              else None) if key == "failed" else "",
            "do": actions(key, project, row)})
    return found


def one(project_id: str) -> dict[str, Any]:
    return videos(only=project_id)[0]


def needs_you() -> int:
    """The sidebar badge: videos waiting for one of your reviews."""
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(Project)
                        .where(Project.status.in_(NEEDS_YOU), Project.archived.is_(False))) or 0


templates.env.globals["needs_you"] = needs_you
templates.env.globals["publish_mode"] = publisher.mode


def _month(text: str | None, now: datetime) -> date:
    try:
        return datetime.strptime(text or "", "%Y-%m").date()
    except ValueError:
        return now.astimezone(zone()).date().replace(day=1)


@router.get("/planner", response_class=HTMLResponse)
def planner(request: Request, error: str | None = None, view: str = "month",
            month: str | None = None) -> HTMLResponse:
    """The calendar: everything with a time, by day (month) or in order (list)."""
    now = datetime.now(UTC)
    items = [v for v in videos() if v["key"] != "cancelled" and not v["archived"] and (
        v["when"] or v["key"] == "failed" and _publish_failed(v))]
    first = _month(month, now)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    by_day: dict[date, list[dict[str, Any]]] = {}
    for item in items:
        if item["when"]:
            by_day.setdefault(item["when"].astimezone(zone()).date(), []).append(item)
    upcoming = sorted((i for i in items if i["key"] not in ("published", "failed")),
                      key=lambda i: i["when"] or now)
    done = sorted((i for i in items if i["key"] == "published"), key=lambda i: i["when"],
                  reverse=True)
    failed = [i for i in items if i["key"] == "failed"]
    previous = (first - timedelta(days=1)).replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    return templates.TemplateResponse(request, "planner.html", {
        "error": error, "view": "list" if view == "list" else "month", "weeks": weeks,
        "by_day": by_day, "first": first, "today": now.astimezone(zone()).date(),
        "previous": previous.strftime("%Y-%m"), "following": following.strftime("%Y-%m"),
        "upcoming": upcoming, "done": done, "failed": failed,
        "lead": config.load()["planner"]["start_hours_before"],
        "min_time": local_input(now + timedelta(minutes=5))})


def _publish_failed(item: dict[str, Any]) -> bool:
    """A video that failed while publishing belongs on the calendar, with Retry."""
    return bool(item["reason"].startswith(plain.STATUS["mock_published"].rstrip("…")))


@router.post("/planner")
async def add_topic(request: Request) -> RedirectResponse:
    """Plan a topic for later: topic, guidelines, duration and an optional publish time."""
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    try:
        topic = Topic(topic=form["topic"], format="short", keywords=metadata.hashtags(
                          form.get("keywords", "")),
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
    return RedirectResponse("/planner?view=list", status_code=303)


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
    return RedirectResponse("/planner?view=list", status_code=303)


def _back(form: dict[str, str], default: str = "/library") -> str:
    """Only our own pages are a return address."""
    back = form.get("back", "")
    return back if back.startswith("/") and not back.startswith("//") else default


def _with(path: str, **query: str) -> str:
    from urllib.parse import quote

    sep = "&" if "?" in path else "?"
    return path + sep + "&".join(f"{k}={quote(v)}" for k, v in query.items())


@router.post("/videos/{project_id}/schedule")
async def set_slot(request: Request, project_id: str) -> RedirectResponse:
    """Schedule, reschedule or (Unschedule) clear a Ready video's slot."""
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    back = _back(form)
    try:
        when = None if form.get("action") == "unschedule" else parse_time(form.get("publish_at",
                                                                                     ""))
        if when is None and form.get("action") != "unschedule":
            raise ValueError("pick a date and time")
        scheduler.schedule(project_id, when, request.state.user["name"])
    except ValueError as error:
        return RedirectResponse(_with(back, error=str(error)), status_code=303)
    return RedirectResponse(back, status_code=303)


@router.post("/videos/{project_id}/publish-now")
async def publish_now(request: Request, project_id: str) -> RedirectResponse:
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    back = _back(form)
    try:
        scheduler.publish_now(project_id, request.state.user["name"])
    except ValueError as error:
        return RedirectResponse(_with(back, error=str(error)), status_code=303)
    return RedirectResponse(back, status_code=303)


@router.post("/videos/{project_id}/metadata")
async def edit_metadata(request: Request, project_id: str) -> RedirectResponse:
    """Edit title / description / hashtags before the upload (audited)."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    back = _back(form)
    try:
        metadata.save(project_id, form.get("title", ""), form.get("description", ""),
                      metadata.hashtags(form.get("hashtags", "")), request.state.user["name"])
    except ValueError as error:
        return RedirectResponse(_with(back, error=str(error)), status_code=303)
    return RedirectResponse(back, status_code=303)


@router.post("/planner/upload")
async def upload(request: Request) -> RedirectResponse:
    """Add an external MP4 (e.g. sir's recording) as a Ready video, approved by hand (D-64)."""
    form = await request.form()
    video, title = form.get("video"), str(form.get("title", "")).strip()
    if not isinstance(video, UploadFile) or not title:
        return RedirectResponse("/library?error=a title and an MP4 file are needed",
                                status_code=303)
    if form.get("approve") != "yes":
        return RedirectResponse("/library?error=tick the approval box: only an approved video "
                                "can be scheduled", status_code=303)
    try:
        project_id = scheduler.upload(title, await video.read(), video.filename or "video.mp4",
                                      request.state.user["name"])
    except ValueError as error:
        return RedirectResponse(f"/library?error={error}", status_code=303)
    return RedirectResponse(f"/library?saved={project_id}", status_code=303)


def schedule(project_id: str, status: str) -> dict[str, Any] | None:
    """For the video page: its slot and what it means now."""
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
