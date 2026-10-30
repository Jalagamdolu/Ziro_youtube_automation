"""Reaper (§7): re-enqueue runs that should be moving but stalled past their stage deadline."""

import time
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.core import config, db
from app.core.log import log
from app.core.models import Event, Job, Project
from app.graph.stages import WORK
from app.jobs.queue import enqueue_once

MOVING = [*WORK, "approved"]  # not at a gate, not done/failed/cancelled


def reap(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    deadlines = config.load()["stage_deadline_seconds"]
    stalled: list[str] = []
    with db.session() as s, s.begin():
        for project in s.scalars(select(Project).where(Project.status.in_(MOVING))):
            last = max(
                s.scalar(select(func.max(Event.at)).where(Event.project_id == project.id))
                or project.created_at,
                s.scalar(select(func.max(Job.started_at)).where(Job.project_id == project.id))
                or project.created_at,
            )
            deadline = deadlines.get(project.status, deadlines["default"])
            if (now - last).total_seconds() < deadline:
                continue
            s.execute(update(Job).where(Job.project_id == project.id, Job.status == "running")
                      .values(status="abandoned", finished_at=now))
            stalled.append(project.id)
    for project_id in stalled:
        log.warning("reaping stalled run", project_id=project_id)
        enqueue_once(f"{project_id}:reap:{int(now.timestamp())}", project_id)
    return stalled


def run_forever() -> None:
    while True:
        try:
            reap()
        except Exception as error:
            log.error("reaper pass failed", error=str(error))
        time.sleep(config.load()["reaper_interval_seconds"])
