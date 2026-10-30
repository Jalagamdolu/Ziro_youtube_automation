"""Review UI (§8): Jinja pages over the same actions as the JSON API. HTMX only refreshes the live
timeline; every decision is a plain form post followed by a redirect.
"""

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select

from app.api import actions
from app.api.actions import CreateRequest, DecisionRequest
from app.core import config, db
from app.core.models import Artifact, Project
from app.graph.stages import REJECT_TARGETS

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, error: str | None = None) -> HTMLResponse:
    with db.session() as s:
        projects = s.scalars(select(Project).order_by(Project.created_at.desc()).limit(25)).all()
    return templates.TemplateResponse(request, "index.html", {"projects": projects,
                                                             "error": error})


@router.post("/ui/projects")
async def create(request: Request) -> RedirectResponse:
    form = await request.form()
    fields = {k: str(v).strip() for k, v in form.items() if str(v).strip()}
    try:
        project_id = actions.create_project(CreateRequest.model_validate(fields))
    except ValidationError as error:
        return _back("/", HTTPException(422, actions.errors(error)))
    except HTTPException as error:
        return _back("/", error)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


@router.get("/ui/projects/{project_id}", response_class=HTMLResponse)
def run_page(request: Request, project_id: str, error: str | None = None,
             submitted: str | None = None) -> HTMLResponse:
    run = actions.run_status(project_id)
    # Decisions resume asynchronously: until the worker moves on, hide the gate just decided.
    waiting = submitted == run["status"]
    with db.session() as s:
        gate = {} if waiting else _gate_context(s, project_id, run["status"])
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "gate": gate, "error": error, "waiting": waiting,
        "reject_targets": REJECT_TARGETS.get(run["status"], []),
    })


@router.get("/ui/projects/{project_id}/live", response_class=HTMLResponse)
def live(request: Request, project_id: str, seen: int) -> HTMLResponse:
    """Polled every 2 s. `seen` is the page's event count: any new transition (even a gate
    reopening after a reject) sends the browser to a fresh page showing the current panel."""
    run = actions.run_status(project_id)
    response = templates.TemplateResponse(request, "_live.html", {"run": run})
    if len(run["events"]) != seen:
        response.headers["HX-Redirect"] = f"/ui/projects/{project_id}"
    return response


@router.post("/ui/projects/{project_id}/decide")
async def decide(request: Request, project_id: str) -> RedirectResponse:
    form = {k: str(v) for k, v in (await request.form()).items()}
    approving = form.get("decision") == "approve"
    kind: Literal["approve", "reject"] = "approve" if approving else "reject"
    body: dict[str, Any] = {"reviewer": form.get("reviewer", "").strip(),
                            "notes": form.get("notes", "").strip(),
                            "target": form.get("target") or None}
    if kind == "approve":
        body |= _claim_edits(project_id, form)
        if form.get("ai_synthetic"):
            body["ai_disclosure"] = {"synthetic": form["ai_synthetic"] == "yes",
                                     "reason": form.get("ai_reason", "").strip()}
    try:
        decision_id = actions.decide(project_id, kind, DecisionRequest.model_validate(body))
    except ValidationError as error:
        return _back(f"/ui/projects/{project_id}", HTTPException(422, actions.errors(error)))
    except HTTPException as error:
        return _back(f"/ui/projects/{project_id}", error)
    gate = decision_id.split(":")[1]
    return RedirectResponse(f"/ui/projects/{project_id}?submitted={gate}", status_code=303)


@router.post("/ui/projects/{project_id}/retry")
def retry(project_id: str) -> RedirectResponse:
    try:
        actions.retry(project_id)
    except HTTPException as error:
        return _back(f"/ui/projects/{project_id}", error)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


@router.post("/ui/projects/{project_id}/cancel")
def cancel(project_id: str) -> RedirectResponse:
    try:
        actions.cancel(project_id)
    except HTTPException as error:
        return _back(f"/ui/projects/{project_id}", error)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


@router.get("/ui/projects/{project_id}/files/{key:path}")
def artifact_file(project_id: str, key: str) -> FileResponse:
    """Serves only files registered as this project's artifacts (no arbitrary paths)."""
    with db.session() as s:
        registered = s.scalar(select(Artifact.id).where(Artifact.project_id == project_id,
                                                        Artifact.storage_path == key))
    if registered is None:
        raise HTTPException(404, "not an artifact of this project")
    return FileResponse(config.runs_dir() / key)


@router.get("/ui/projects/{project_id}/bundle.zip")
def bundle(project_id: str) -> Response:
    """Download bundle: the newest non-stale version of every artifact, by stage."""
    with db.session() as s:
        actions.get_project(s, project_id)
        latest = actions.latest_artifacts(s, project_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for (stage, name), key in sorted(latest.items()):
            archive.write(config.runs_dir() / key, f"{stage}/{name}")
    return Response(buffer.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="ziro-run-{project_id}.zip"'})


def _gate_context(s: Any, project_id: str, status: str) -> dict[str, Any]:
    """What the gate panel shows; empty when the run is not at a gate."""
    files = {name: key for (_, name), key in actions.latest_artifacts(s, project_id).items()}

    def load(name: str) -> Any:
        text = actions.read_latest(s, project_id, name)
        return json.loads(text) if text else None

    if status == "research_review":
        return {"claims": load("claims.json") or []}
    if status == "script_review":
        lint = {t["title"]: t for t in load("title_lint.json") or []}
        return {"package": load("content_package.json"), "title_lint": lint}
    if status == "qa_review":
        return {"package": load("content_package.json"), "qa_report": load("qa_report.json"),
                "video": files.get("video.mp4"), "thumbnail": files.get("thumbnail.png")}
    return {}


def _claim_edits(project_id: str, form: dict[str, str]) -> dict[str, Any]:
    """Per-claim choices from the research_review form: action_<id> and text_<id> (D-20)."""
    with db.session() as s:
        claims = json.loads(actions.read_latest(s, project_id, "claims.json") or "[]")
    removed = [c["id"] for c in claims if form.get(f"action_{c['id']}") == "remove"]
    edited = {c["id"]: form[f"text_{c['id']}"].strip() for c in claims
              if c["id"] not in removed and f"text_{c['id']}" in form
              and form[f"text_{c['id']}"].strip() not in ("", c["claim"])}
    return {"removed_claims": removed, "edited_claims": edited}


def _back(path: str, error: HTTPException) -> RedirectResponse:
    detail = error.detail if isinstance(error.detail, str) else "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg')}" for e in error.detail)
    return RedirectResponse(f"{path}?error={quote(detail)}", status_code=303)
