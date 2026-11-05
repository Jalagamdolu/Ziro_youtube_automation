"""Topic scheduler (D-47): APScheduler in the API process checks the planner every minute.

- A planned topic's run starts `planner.start_hours_before` (3 h) before its publish_at, so both
  reviews fit; "Run now" starts it at once through the same path.
- A run from a topic publishes (mock) at publish_at, never earlier: after the final approval it
  waits at export_ready, and this scheduler resumes it when the time comes.
- Nothing publishes without both reviews: the Publisher refuses a run without an approved
  qa_review (D-06). A run still in review at publish_at just keeps waiting; once approved late it
  publishes straight away, and the planner shows the missed time.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.core import config, db
from app.core.log import log
from app.core.models import Project, Topic
from app.jobs.queue import enqueue_once

WAITING = "export_ready"  # a scheduled run that is approved and waits for its publish time


def start_topic(topic_id: int, actor: str) -> str | None:
    """Create the topic's run once (a planned topic only); returns the project id."""
    from app.api import actions  # actions imports the graph stages; keep this module light

    with db.session() as s, s.begin():
        claimed = s.execute(update(Topic).where(Topic.id == topic_id, Topic.status == "planned")
                            .values(status="starting")).rowcount  # type: ignore[attr-defined]
        topic = s.get_one(Topic, topic_id)
        request = actions.CreateRequest(
            prompt=topic.topic, format="long" if topic.format == "long" else "short",
            target_seconds=topic.target_seconds, keywords=topic.keywords,
            guidelines=topic.guidelines, owner=actor)
    if not claimed:
        return None
    try:
        project_id = actions.create_project(request)
    except Exception:
        with db.session() as s, s.begin():
            s.execute(update(Topic).where(Topic.id == topic_id).values(status="planned"))
        raise
    with db.session() as s, s.begin():
        s.execute(update(Topic).where(Topic.id == topic_id)
                  .values(status="started", project_id=project_id))
    log.info("topic run started", topic_id=topic_id, project_id=project_id, actor=actor)
    return project_id


def start_due(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    lead = timedelta(hours=config.load()["planner"]["start_hours_before"])
    with db.session() as s:
        due = s.scalars(select(Topic.id).where(Topic.status == "planned",
                                               Topic.publish_at <= now + lead)).all()
    return [p for topic_id in due if (p := start_topic(topic_id, "scheduler"))]


def publish_at(project_id: str) -> datetime | None:
    with db.session() as s:
        return s.scalar(select(Topic.publish_at).where(Topic.project_id == project_id))


def publish_due(now: datetime | None = None) -> list[str]:
    """Resume approved runs waiting at export_ready whose publish time has come."""
    now = now or datetime.now(UTC)
    with db.session() as s:
        due = s.scalars(select(Project.id).join(Topic, Topic.project_id == Project.id).where(
            Project.status == WAITING, Topic.publish_at <= now)).all()
    resumed = [p for p in due if enqueue_once(f"{p}:publish:1", p, {"due": True})]
    for project_id in resumed:
        log.info("publish time reached, resuming", project_id=project_id)
    return resumed


def waiting_for_publish(project: Project, now: datetime) -> bool:
    """For the reaper: an approved run parked until its publish time is not stalled."""
    when = publish_at(project.id) if project.status == WAITING else None
    return when is not None and when > now


def tick() -> dict[str, Any]:
    started, published = start_due(), publish_due()
    return {"started": started, "published": published}


def start() -> Any:
    """The APScheduler job, started from the API's lifespan."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_safe_tick, "interval", seconds=config.load()["planner"]["check_seconds"],
                      next_run_time=datetime.now(UTC))
    scheduler.start()
    return scheduler


def _safe_tick() -> None:
    try:
        tick()
    except Exception as error:
        log.error("scheduler tick failed", error=str(error))
