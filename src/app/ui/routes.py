"""Product UI (§8, D-22, D-31): prompt -> gates -> playable video in one browser tab. Jinja pages
over the same actions as the JSON API; HTMX only refreshes the live timeline; every decision is a
plain form post followed by a redirect. The API never runs the graph inline.
"""

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from starlette.datastructures import UploadFile  # what request.form() returns for files

from app.adapters import storage
from app.api import actions
from app.api.actions import CreateRequest, DecisionRequest
from app.core import config, db
from app.core.contracts import ContentPackage, HookDraft, PackageDraft
from app.core.models import Artifact, Cost, Project
from app.graph.stages import GATES, ORDER, REJECT_TARGETS
from app.nodes import human_edit, script_checks
from app.nodes.rendering import PHOTO_CHOICES, RECORDING

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["mode"] = lambda: config.load()["mode"]
MAX_RECORDING_BYTES = 600_000_000  # a few minutes of phone video
# Finished-run downloads: file name -> button label (the export bundle, one file at a time).
DOWNLOADS = {"video.mp4": "Video (MP4)", "captions.srt": "Captions (SRT)",
             "captions.vtt": "Captions (VTT)", "thumbnail.png": "Thumbnail",
             "content_package.json": "Metadata (content package)", "claims.json": "Claims",
             "publish_receipt.json": "Publish receipt (mock)", "cost_report.json": "Cost report"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request, error: str | None = None) -> HTMLResponse:
    """First visit: the prompt box. After that: every run, newest first."""
    with db.session() as s:
        spent = dict(s.execute(select(Cost.project_id, func.sum(Cost.amount))
                               .group_by(Cost.project_id)).all())
        projects = s.scalars(select(Project).order_by(Project.created_at.desc())).all()
    if not projects:
        return new(request, error)
    return templates.TemplateResponse(request, "runs.html", {
        "projects": projects, "spent": spent, "error": error})


@router.get("/new", response_class=HTMLResponse)
def new(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"error": error})


@router.post("/ui/projects")
async def create(request: Request) -> RedirectResponse:
    form = await request.form()
    fields = {k: str(v).strip() for k, v in form.items() if str(v).strip()}
    try:
        project_id = actions.create_project(CreateRequest.model_validate(fields))
    except ValidationError as error:
        return _back("/new", HTTPException(422, actions.errors(error)))
    except HTTPException as error:
        return _back("/new", error)
    return RedirectResponse(f"/ui/projects/{project_id}", status_code=303)


@router.get("/ui/projects/{project_id}", response_class=HTMLResponse)
def run_page(request: Request, project_id: str, error: str | None = None,
             submitted: str | None = None) -> HTMLResponse:
    run = actions.run_status(project_id)
    # Decisions resume asynchronously: until the worker moves on, hide the gate just decided.
    waiting = submitted == run["status"]
    with db.session() as s:
        gate = {} if waiting else _gate_context(s, project_id, run["status"])
        finish = _finish(s, project_id) if run["status"] == "done" else {}
        recording = _recording_context(s, run)
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "gate": gate, "error": error, "waiting": waiting, "finish": finish,
        "recording": recording,
        "stages": stages(run), "edit": None if waiting else _edit_text(run),
        "reject_targets": REJECT_TARGETS.get(run["status"], []),
    })


@router.get("/ui/projects/{project_id}/live", response_class=HTMLResponse)
def live(request: Request, project_id: str, seen: int) -> HTMLResponse:
    """Polled every 2 s. `seen` is the page's event count: any new transition (even a gate
    reopening after a reject) sends the browser to a fresh page showing the current panel."""
    run = actions.run_status(project_id)
    response = templates.TemplateResponse(request, "_live.html", {"run": run,
                                                                  "stages": stages(run)})
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


@router.post("/ui/projects/{project_id}/edit")
async def edit(request: Request, project_id: str) -> RedirectResponse:
    """The human-edit bridge (D-30) from the browser: the edited package replaces the model for
    one scripting run and goes through every check. At script_review this is a reject to
    scripting; after a failed scripting run it is a retry."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    reviewer = form.get("reviewer", "").strip() or "Dolender"
    text = re.sub(r"(=== EDITED BY ===\n)[^\n]*", lambda m: m.group(1) + reviewer,
                  form.get("text", "").replace("\r\n", "\n"))
    page = f"/ui/projects/{project_id}"
    try:
        human_edit.parse(text)
    except ValueError as error:
        return _back(page, HTTPException(422, f"the edited script can't be read: {error}"))
    run = actions.run_status(project_id)
    if run["status"] not in ("script_review", "failed") or (
            run["status"] == "failed" and _failed_stage(run) != "scripting"):
        return _back(page, HTTPException(409, "a script can be hand-edited at script_review or "
                                              "after scripting fails"))
    storage.get().write(human_edit.KEY.format(project_id), text.encode("utf-8"))
    try:
        if run["status"] == "script_review":
            actions.decide(project_id, "reject", DecisionRequest(
                reviewer=reviewer, target="scripting",
                notes=f"Hand-edited script submitted by {reviewer}; it runs through every check."))
            return RedirectResponse(f"{page}?submitted=script_review", status_code=303)
        actions.retry(project_id)
    except HTTPException as error:
        return _back(page, error)
    return RedirectResponse(page, status_code=303)


@router.post("/ui/projects/{project_id}/recording")
async def upload_recording(request: Request, project_id: str) -> RedirectResponse:
    """The presenter's phone recording of the approved script (D-36). Stored for the run; after
    rendering stopped for it the run retries, and at qa_review it counts as a re-take."""
    form = await request.form()
    video, reviewer = form.get("video"), str(form.get("reviewer", "")).strip() or "Dolender"
    page = f"/ui/projects/{project_id}"
    if not isinstance(video, UploadFile) or not video.filename:
        return _back(page, HTTPException(422, "choose the video file to upload"))
    data = await video.read(MAX_RECORDING_BYTES + 1)
    if len(data) > MAX_RECORDING_BYTES or not data:
        return _back(page, HTTPException(413, "the recording must be a video under 600 MB"))
    run = actions.run_status(project_id)
    status, failed = run["status"], _failed_stage(run)
    if status not in ("script_review", "qa_review") and not (
            status == "failed" and failed == "rendering"):
        return _back(page, HTTPException(409, "upload the recording at script_review, at "
                                              "qa_review, or when rendering waits for it"))
    storage.get().write(RECORDING.format(project_id), data)
    try:
        if status == "failed":
            actions.retry(project_id)
        elif status == "qa_review":
            actions.decide(project_id, "reject", DecisionRequest(
                reviewer=reviewer, target="rendering",
                notes=f"New presenter recording uploaded by {reviewer}."))
            return RedirectResponse(f"{page}?submitted=qa_review", status_code=303)
    except HTTPException as error:
        return _back(page, error)
    return RedirectResponse(page, status_code=303)


@router.post("/ui/projects/{project_id}/photo")
async def swap_photo(request: Request, project_id: str) -> RedirectResponse:
    """qa_review: use another candidate photo for one scene (D-34). The choice is stored and the
    run goes back to rendering with a note naming the reviewer and the swap."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    reviewer = form.get("reviewer", "").strip() or "Dolender"
    scene, index = form.get("scene", ""), int(form.get("index", "0") or 0)
    page = f"/ui/projects/{project_id}"
    if actions.run_status(project_id)["status"] != "qa_review":
        return _back(page, HTTPException(409, "photos can be swapped at qa_review"))
    store, key = storage.get(), PHOTO_CHOICES.format(project_id)
    choices = json.loads(store.read(key)) if store.exists(key) else {}
    store.write(key, json.dumps(choices | {scene: index}).encode("utf-8"))
    try:
        actions.decide(project_id, "reject", DecisionRequest(
            reviewer=reviewer, target="rendering",
            notes=f"Photo swap by {reviewer}: scene {scene} uses candidate {index + 1}."))
    except HTTPException as error:
        return _back(page, error)
    return RedirectResponse(f"{page}?submitted=qa_review", status_code=303)


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
                "video": files.get("video.mp4"), "thumbnail": files.get("thumbnail.png"),
                "photos": (load("stock.json") or {}).get("scenes", [])}
    return {}


def stages(run: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per stage in order: what happened there, how many attempts, how long it took."""
    rows = []
    for stage in (s for s in ORDER if s != "approved"):
        if stage in GATES:
            decided = [a for a in run["approvals"] if a["stage"] == stage]
            state = ("waiting for you" if run["status"] == stage else
                     f"{decided[-1]['decision']}d" if decided else "pending")
            rows.append({"stage": stage, "state": state, "attempts": len(decided),
                         "seconds": None, "gate": True})
            continue
        jobs = [j for j in run["jobs"] if j["stage"] == stage]
        seconds = sum((j["finished_at"] - j["started_at"]).total_seconds()
                      for j in jobs if j["finished_at"])
        rows.append({"stage": stage, "state": jobs[-1]["status"] if jobs else "pending",
                     "attempts": len(jobs), "seconds": seconds if jobs else None, "gate": False,
                     "failed": sum(j["status"] == "failed" for j in jobs)})
    return rows


def _recording_context(s: Any, run: dict[str, Any]) -> dict[str, Any] | None:
    """Presenter runs (D-36): the narration to read on camera and whether a take is uploaded."""
    brief = json.loads(actions.read_latest(s, run["id"], "brief.json") or "{}")
    status = run["status"]
    if not brief.get("presenter") or not (
            status in ("script_review", "qa_review")
            or (status == "failed" and _failed_stage(run) == "rendering")):
        return None
    package = json.loads(actions.read_latest(s, run["id"], "content_package.json") or "{}")
    lines = [(name, " ".join(script_checks.MARKER.sub("", line).strip() for line in narration))
             for name, narration in script_checks.sections(package.get("script", "")).items()]
    key = RECORDING.format(run["id"])
    return {"lines": lines, "uploaded": storage.get().exists(key),
            "seconds": package.get("brief", {}).get("target_seconds")}


def _failed_stage(run: dict[str, Any]) -> str | None:
    failed = [j for j in run["jobs"] if j["status"] == "failed"]
    return failed[-1]["stage"] if failed else None


def _edit_text(run: dict[str, Any]) -> str | None:
    """The editable package for the hand-edit box, or None where editing doesn't apply. After a
    failed scripting run it is the last draft, annotated with the rules it broke."""
    project_id = run["id"]
    if run["status"] == "failed" and _failed_stage(run) == "scripting":
        store, key = storage.get(), human_edit.LAST_FAILED.format(project_id)
        if store.exists(key):  # the draft that failed (model or hand-edited), flagged per rule
            return store.read(key).decode("utf-8")
    elif run["status"] != "script_review":
        return None
    with db.session() as s:
        newest = s.scalars(select(Artifact.storage_path).where(
            Artifact.project_id == project_id, Artifact.stage == "scripting",
            Artifact.type == "content_package.json").order_by(Artifact.version.desc())).first()
    if newest is None:
        return None
    package = ContentPackage.model_validate_json(storage.get().read(newest))
    draft = PackageDraft(script=package.script, titles=package.titles,
                         hooks=[HookDraft(text=h.text, explanation=h.explanation)
                                for h in package.hooks],
                         thumbnail_text=package.thumbnail_text, description=package.description,
                         tags=package.tags, target_queries=package.target_queries,
                         chapters=package.chapters)
    return human_edit.render(draft, [], "Dolender")


def _finish(s: Any, project_id: str) -> dict[str, Any]:
    """A finished run: the video, one download per export file, and what it cost."""
    files = {name: key for (_, name), key in actions.latest_artifacts(s, project_id).items()}
    costs = s.execute(select(Cost.provider, Cost.observed_or_estimate, func.count(),
                             func.sum(Cost.units), func.sum(Cost.amount))
                      .where(Cost.project_id == project_id)
                      .group_by(Cost.provider, Cost.observed_or_estimate)
                      .order_by(Cost.provider)).all()
    return {"video": files.get("video.mp4"), "thumbnail": files.get("thumbnail.png"),
            "downloads": [(label, files[name]) for name, label in DOWNLOADS.items()
                          if name in files],
            "costs": costs}


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
