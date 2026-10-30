"""Writes to the audit tables. Callers own the session and commit."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.models import Approval, Artifact, Event, Job, Project, now


def transition(s: Session, project_id: str, to_state: str, actor: str = "system") -> None:
    project = s.get_one(Project, project_id)
    if project.status == to_state:
        return
    s.add(Event(project_id=project_id, from_state=project.status, to_state=to_state, actor=actor))
    project.status = to_state


def start_job(s: Session, project_id: str, stage: str) -> Job:
    previous = s.scalar(
        select(func.count()).where(Job.project_id == project_id, Job.stage == stage)
    )
    job = Job(project_id=project_id, stage=stage, status="running", retry_count=previous or 0)
    s.add(job)
    s.flush()
    return job


def finish_job(s: Session, job_id: int, status: str, error: BaseException | None = None) -> None:
    job = s.get_one(Job, job_id)
    job.status = status
    job.finished_at = now()
    if error is not None:
        job.error_code = type(error).__name__
        job.error_message = str(error)


def latest_version(s: Session, project_id: str, stage: str) -> int:
    version = s.scalar(
        select(func.max(Artifact.version)).where(
            Artifact.project_id == project_id, Artifact.stage == stage
        )
    )
    return version or 0


def mark_stale(s: Session, project_id: str, stages: list[str]) -> None:
    s.execute(
        update(Artifact)
        .where(Artifact.project_id == project_id, Artifact.stage.in_(stages))
        .values(stale=True)
    )


def gate_opened_at(s: Session, project_id: str, gate: str) -> datetime:
    opened = s.scalar(
        select(func.max(Event.at)).where(Event.project_id == project_id, Event.to_state == gate)
    )
    if opened is None:
        raise LookupError(f"{gate} never opened for {project_id}")
    return opened


def gate_openings(s: Session, project_id: str, gate: str) -> int:
    count = s.scalar(
        select(func.count()).where(Event.project_id == project_id, Event.to_state == gate)
    )
    return count or 0


def decision_recorded(s: Session, decision_id: str) -> bool:
    return s.scalar(select(Approval.id).where(Approval.decision_id == decision_id)) is not None
