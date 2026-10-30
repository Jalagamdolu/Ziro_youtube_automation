"""Run actions shared by the JSON API, the review UI and the CLI. They only validate and enqueue;
the graph never runs inline (§7). Errors are HTTPExceptions so every caller reports them alike.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import storage
from app.core import audit, config, costs, db
from app.core.contracts import AiDisclosure, Brief, Decision
from app.core.models import Approval, Artifact, Event, Job, Project
from app.graph.stages import CANCELLED, DONE, FAILED, GATES, REJECT_TARGETS
from app.jobs.queue import enqueue_once

DEFAULT_SECONDS = {"short": 60, "long": 240}


class CreateRequest(BaseModel):
    prompt: str
    format: Literal["short", "long"]
    owner: str = "dolender"
    audience: str = "Indian students, early-career developers and career switchers"
    language: str = "en"
    cta: str = "Explore AI learning at ziro.digital"
    target_seconds: int | None = None
    learning_outcome: str | None = None


class DecisionRequest(BaseModel):
    reviewer: str
    notes: str = ""
    target: str | None = None
    ai_disclosure: AiDisclosure | None = None
    removed_claims: list[str] = []  # research_review only (D-20)
    edited_claims: dict[str, str] = {}


def create_project(request: CreateRequest) -> str:
    try:
        brief = Brief(
            topic=request.prompt,
            audience=request.audience,
            learning_outcome=request.learning_outcome or request.prompt,
            language=request.language,
            format=request.format,
            target_seconds=request.target_seconds or DEFAULT_SECONDS[request.format],
            cta=request.cta,
        )
    except ValidationError as error:
        raise HTTPException(422, errors(error)) from error
    project_id = uuid.uuid4().hex
    with db.session() as s, s.begin():
        s.add(Project(id=project_id, owner=request.owner, topic=brief.topic,
                      audience=brief.audience, language=brief.language, format=brief.format,
                      target_seconds=brief.target_seconds, cta=brief.cta, status="draft"))
        s.flush()
        s.add(Event(project_id=project_id, from_state=None, to_state="draft",
                    actor=request.owner))
    store = storage.get()
    payload = {"prompt": request.prompt, "brief": brief.model_dump()}
    store.write(f"{project_id}/request.json", json.dumps(payload, indent=2).encode("utf-8"))
    store.write(f"{project_id}/config.yaml", config.CONFIG_PATH.read_bytes())  # run snapshot
    enqueue_once(f"{project_id}:draft:1", project_id)
    return project_id


def run_status(project_id: str) -> dict[str, Any]:
    with db.session() as s:
        project = get_project(s, project_id)

        def rows(model: Any, order: Any) -> list[dict[str, Any]]:
            found = s.scalars(select(model).where(model.project_id == project_id).order_by(order))
            return [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in found]

        return {
            "id": project.id,
            "status": project.status,
            "brief": {"topic": project.topic, "audience": project.audience,
                      "language": project.language, "format": project.format,
                      "target_seconds": project.target_seconds, "cta": project.cta},
            "awaiting_gate": project.status if project.status in GATES else None,
            "total_cost_usd": costs.total(s, project_id),
            "events": rows(Event, Event.id),
            "jobs": rows(Job, Job.id),
            "approvals": rows(Approval, Approval.id),
            "artifacts": rows(Artifact, Artifact.id),
        }


def decide(project_id: str, kind: Literal["approve", "reject"], body: DecisionRequest) -> str:
    """Validate a gate decision and enqueue its resume once; returns the decision id."""
    with db.session() as s:
        gate = get_project(s, project_id).status
        if gate not in GATES:
            raise HTTPException(409, f"run is not at a gate (status: {gate})")
        opening = audit.gate_openings(s, project_id, gate)
        touched = set(body.removed_claims) | set(body.edited_claims)
        if touched and gate == "research_review":
            claims = json.loads(read_latest(s, project_id, "claims.json") or "[]")
            unknown = touched - {c["id"] for c in claims}
            if unknown:
                raise HTTPException(422, f"unknown claim ids: {', '.join(sorted(unknown))}")
    if kind == "reject" and body.target not in REJECT_TARGETS[gate]:
        raise HTTPException(422, f"{gate} can reject to: {', '.join(REJECT_TARGETS[gate])}")
    decision_id = f"{project_id}:{gate}:{opening}"
    try:
        decision = Decision(decision_id=decision_id, gate=gate, decision=kind,
                            decided_at=datetime.now(UTC), **body.model_dump())
    except ValidationError as error:
        raise HTTPException(422, errors(error)) from error
    if not enqueue_once(decision_id, project_id, decision.model_dump(mode="json")):
        raise HTTPException(409, "a decision for this gate was already submitted")
    return decision_id


def retry(project_id: str) -> str:
    with db.session() as s:
        if get_project(s, project_id).status != FAILED:
            raise HTTPException(409, "only failed runs can be retried")
        attempt = audit.gate_openings(s, project_id, FAILED)  # count of failures so far
    job_id = f"{project_id}:retry:{attempt}"
    if not enqueue_once(job_id, project_id):
        raise HTTPException(409, "retry already submitted")
    return job_id


def cancel(project_id: str) -> None:
    with db.session() as s, s.begin():
        if get_project(s, project_id).status in (DONE, CANCELLED):
            raise HTTPException(409, "run already finished")
        audit.transition(s, project_id, CANCELLED, actor="api")


def latest_artifacts(s: Session, project_id: str) -> dict[tuple[str, str], str]:
    """(stage, file name) -> storage key of the newest non-stale version."""
    rows = s.scalars(select(Artifact).where(Artifact.project_id == project_id,
                                            Artifact.stale.is_(False))
                     .order_by(Artifact.version))
    return {(a.stage, a.type): a.storage_path for a in rows}


def read_latest(s: Session, project_id: str, name: str) -> str | None:
    keys = [key for (_, file), key in latest_artifacts(s, project_id).items() if file == name]
    return storage.get().read(keys[-1]).decode("utf-8") if keys else None


def get_project(s: Session, project_id: str) -> Project:
    project = s.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def errors(error: ValidationError) -> list[Any]:
    return list(error.errors(include_url=False, include_input=False, include_context=False))
