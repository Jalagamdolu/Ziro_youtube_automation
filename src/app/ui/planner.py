"""Topic planner and login pages (D-47). The planner lists planned videos with what each one is
waiting for; the admin adds topics and can start one now through the scheduler's own path."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.core import config, db
from app.core.models import Project, Topic
from app.graph.stages import GATES
from app.jobs import scheduler
from app.ui import auth
from app.ui.routes import templates

router = APIRouter()


def zone() -> timezone:
    offset = config.load()["planner"]["utc_offset"]  # "+05:30"
    delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
    return timezone(-delta if offset.startswith("-") else delta)


def shown(moment: datetime) -> str:
    return moment.astimezone(zone()).strftime("%a %d %b, %H:%M") + " IST"


def state(topic: Topic, status: str | None, now: datetime) -> tuple[str, str]:
    """(what the topic is waiting for, pill class). A missed publish time is said loudly."""
    lead = timedelta(hours=config.load()["planner"]["start_hours_before"])
    late = now >= topic.publish_at
    if topic.status == "cancelled":
        return "cancelled", ""
    if topic.status in ("planned", "starting"):
        return f"planned · run starts {shown(topic.publish_at - lead)}", ""
    if status == "done":
        return "published (mock)", "ok"
    if status == scheduler.WAITING:
        return ("approved · publishes " + shown(topic.publish_at), "ok") if not late \
            else ("publishing now", "ok")
    if status in ("failed", "cancelled"):
        return f"run {status} · nothing published", "bad"
    doing = f"waiting for your {status.replace('_', ' ')}" if status in GATES \
        else f"running: {status}"
    if late:
        return f"MISSED publish time · nothing published · {doing}", "bad"
    return doing, "warn"


@router.get("/planner", response_class=HTMLResponse)
def planner(request: Request, error: str | None = None) -> HTMLResponse:
    now = datetime.now(UTC)
    with db.session() as s:
        topics = s.scalars(select(Topic).order_by(Topic.publish_at)).all()
        statuses = dict(s.execute(select(Project.id, Project.status)).all())
    rows = [{"topic": t, "when": shown(t.publish_at),
             "state": state(t, statuses.get(t.project_id or ""), now)} for t in topics]
    default = (now + timedelta(days=1)).astimezone(zone()).strftime("%Y-%m-%dT18:00")
    return templates.TemplateResponse(request, "planner.html", {
        "rows": rows, "error": error, "default_time": default,
        "admin": request.state.user["role"] == "admin",
        "lead": config.load()["planner"]["start_hours_before"]})


@router.post("/planner")
async def add_topic(request: Request) -> RedirectResponse:
    _admin(request)
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    try:
        when = datetime.fromisoformat(form["publish_at"]).replace(tzinfo=zone()).astimezone(UTC)
        topic = Topic(topic=form["topic"], format=form.get("format", "short"),
                      keywords=[k.strip() for k in form.get("keywords", "").split(",")
                                if k.strip()],
                      guidelines=form.get("guidelines", ""), publish_at=when, status="planned",
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
    _admin(request)
    try:
        project_id = scheduler.start_topic(topic_id, request.state.user["name"])
    except HTTPException as error:
        return RedirectResponse(f"/planner?error={error.detail}", status_code=303)
    if project_id is None:
        return RedirectResponse("/planner?error=that topic has already started", status_code=303)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


@router.post("/planner/{topic_id}/cancel")
def cancel_topic(request: Request, topic_id: int) -> RedirectResponse:
    _admin(request)
    with db.session() as s, s.begin():
        topic = s.get(Topic, topic_id)
        if topic and topic.status == "planned":
            topic.status = "cancelled"
    return RedirectResponse("/planner", status_code=303)


def _admin(request: Request) -> None:
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "only the admin plans topics")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {
        "next": next if next.startswith("/") else "/", "error": error,
        "configured": bool(auth.users())})


@router.post("/login")
async def login(request: Request) -> RedirectResponse:
    form = {k: str(v) for k, v in (await request.form()).items()}
    role = auth.check(form.get("username", "").strip(), form.get("password", ""))
    target = form.get("next", "/") if form.get("next", "/").startswith("/") else "/"
    if role is None:
        return RedirectResponse(f"/login?error=wrong name or password&next={target}",
                                status_code=303)
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(auth.COOKIE, auth.cookie(form["username"].strip(), role),
                        httponly=True, samesite="lax", max_age=auth.HOURS * 3600)
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.COOKIE)
    return response


def schedule(project_id: str, status: str) -> dict[str, Any] | None:
    """For the run page: the planned publish time and whether it was missed."""
    when = scheduler.publish_at(project_id)
    if when is None:
        return None
    return {"when": shown(when), "missed": datetime.now(UTC) >= when and status != "done",
            "waiting": status == scheduler.WAITING}
