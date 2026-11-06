"""Product UI (§8, D-22, D-31): prompt -> gates -> playable video in one browser tab. Jinja pages
over the same actions as the JSON API; HTMX only refreshes the live timeline; every decision is a
plain form post followed by a redirect. The API never runs the graph inline.
"""

import hashlib
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

from app.adapters import storage
from app.api import actions
from app.api.actions import CreateRequest, DecisionRequest
from app.core import config, db, engines
from app.core.contracts import ContentPackage, HookDraft, PackageDraft
from app.core.models import Artifact, Cost
from app.graph.stages import GATES, ORDER, REJECT_TARGETS
from app.nodes import human_edit, script_checks
from app.nodes.rendering import PHOTO_CHOICES
from app.ui import plain

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["mode"] = lambda: config.load()["mode"]
templates.env.globals["banners"] = engines.banners  # missing keys, said on every page (D-46)
templates.env.globals["plain"] = plain  # the product view's words (D-63)
# The stylesheet's URL carries its content hash, so a browser never keeps a stale copy.
templates.env.globals["css_version"] = hashlib.sha256(
    (Path(__file__).parent / "static" / "theme.css").read_bytes()).hexdigest()[:10]
# Finished-run downloads: file name -> button label (the export bundle, one file at a time).
DURATIONS = ("30", "40", "50", "60")  # New Video's length picker; 60 s is the ceiling (D-62)
DOWNLOADS = {"video.mp4": "Video (MP4)", "captions.srt": "Captions (SRT)",
             "captions.vtt": "Captions (VTT)", "thumbnail.png": "Thumbnail",
             "content_package.json": "Metadata (content package)", "claims.json": "Claims",
             "publish_receipt.json": "Publish receipt", "cost_report.json": "Cost report"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request, error: str | None = None) -> HTMLResponse:
    """Home is the Library: every video, the ones waiting for you first (D-69)."""
    from app.ui import library  # library renders with this module's templates

    return library.library(request, error=error)


@router.get("/new", response_class=HTMLResponse)
def new(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"error": error})


@router.post("/ui/projects")
async def create(request: Request) -> RedirectResponse:
    """New Video (D-69): prompt, optional keywords and guidelines, 30/40/50/60 s. Shorts only
    until long templates exist; 60 s is a hard ceiling (D-62)."""
    from app.core import metadata

    form = await request.form()
    fields: dict[str, Any] = {k: str(v).strip() for k, v in form.items() if str(v).strip()}
    fields["format"] = "short"
    if "keywords" in fields:
        fields["keywords"] = metadata.hashtags(fields["keywords"])
    if fields.get("target_seconds") not in (None, *DURATIONS):
        return _back("/new", HTTPException(422, "pick a length of 30, 40, 50 or 60 seconds"))
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
        finish = _finish(s, project_id) if run["status"] in ("done", "export_ready") else {}
        script = actions.read_latest(s, project_id, "script.md")
        tech = _technical(s, project_id)
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "gate": gate, "error": error, "waiting": waiting, "finish": finish,
        "tech": tech, "script": script, "step": generating_step(run),
        "video": _video(project_id),
        "stages": stages(run), "edit": None if waiting else _edit_text(run),
        "reject_targets": REJECT_TARGETS.get(run["status"], []),
        "schedule": _schedule(project_id, run["status"]),
    })


@router.get("/ui/projects/{project_id}/live", response_class=HTMLResponse)
def live(request: Request, project_id: str, seen: int) -> HTMLResponse:
    """Polled every 2 s. `seen` is the page's event count: any new transition (even a gate
    reopening after a reject) sends the browser to a fresh page showing the current panel."""
    run = actions.run_status(project_id)
    response = templates.TemplateResponse(request, "_live.html", {
        "run": run, "stages": stages(run), "step": generating_step(run),
        "video": _video(project_id)})
    if len(run["events"]) != seen:
        response.headers["HX-Redirect"] = f"/ui/projects/{project_id}"
    return response


@router.post("/ui/projects/{project_id}/decide")
async def decide(request: Request, project_id: str) -> RedirectResponse:
    form = {k: str(v) for k, v in (await request.form()).items()}
    approving = form.get("decision") == "approve"
    kind: Literal["approve", "reject"] = "approve" if approving else "reject"
    body: dict[str, Any] = {"reviewer": request.state.user["name"],  # the reviewer (D-61)
                            "notes": form.get("notes", "").strip(),
                            "target": form.get("target") or None}
    if form.get("decision") == "regenerate":  # D-69: a rewrite (or new research), notes optional
        body["target"] = "researching" if form.get("target") == "researching" else "scripting"
        body["notes"] = body["notes"] or "Regenerate the script (no notes given)."
    if kind == "approve" and form.get("ai_synthetic"):
        body["ai_disclosure"] = {"synthetic": form["ai_synthetic"] == "yes",
                                 "reason": form.get("ai_reason", "").strip()}
    page = _return_to(form, f"/ui/projects/{project_id}")  # the run page or the planner (D-66)
    try:
        decision_id = actions.decide(project_id, kind, DecisionRequest.model_validate(body))
    except ValidationError as error:
        return _back(page, HTTPException(422, actions.errors(error)))
    except HTTPException as error:
        return _back(page, error)
    gate = decision_id.split(":")[1]
    if gate == "qa_review" and approving and page.startswith("/ui/"):
        return RedirectResponse(f"/library?saved={project_id}", status_code=303)  # D-69 toast
    submitted = gate if page.startswith("/ui/") else f"{project_id}:{gate}"
    return RedirectResponse(f"{page}?submitted={submitted}", status_code=303)


@router.post("/ui/projects/{project_id}/edit")
async def edit(request: Request, project_id: str) -> RedirectResponse:
    """The human-edit bridge (D-30) from the browser: the edited package replaces the model for
    one scripting run and goes through every check. At script_review this is a reject to
    scripting; after a failed scripting run it is a retry."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    reviewer = request.state.user["name"]
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
                # The edit's fingerprint keys the stage cache: a second, different edit re-runs.
                notes=f"Hand-edited script submitted by {reviewer} (edit "
                      f"{hashlib.sha256(text.encode()).hexdigest()[:8]}); it runs through every "
                      "check."))
            return RedirectResponse(f"{page}?submitted=script_review", status_code=303)
        actions.retry(project_id)
    except HTTPException as error:
        return _back(page, error)
    return RedirectResponse(page, status_code=303)


@router.post("/ui/projects/{project_id}/photo")
async def swap_photo(request: Request, project_id: str) -> RedirectResponse:
    """qa_review: use another candidate photo for one scene (D-34). The choice is stored and the
    run goes back to rendering with a note naming the reviewer and the swap."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    reviewer = request.state.user["name"]
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
async def retry(request: Request, project_id: str) -> RedirectResponse:
    page = _return_to({k: str(v) for k, v in (await request.form()).items()},
                      f"/ui/projects/{project_id}")
    try:
        actions.retry(project_id)
    except HTTPException as error:
        return _back(page, error)
    return RedirectResponse(page, status_code=303)


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

    if status == "script_review":
        lint = {t["title"]: t for t in load("title_lint.json") or []}
        package, support = load("content_package.json"), load("support_flags.json")
        return {"package": package, "title_lint": lint, "support": support,
                "script_lines": script_lines(package["script"], support, package["claims"])}
    if status == "qa_review":
        return {"package": load("content_package.json"), "qa_report": load("qa_report.json"),
                "video": files.get("video.mp4"), "thumbnail": files.get("thumbnail.png"),
                "photos": (load("stock.json") or {}).get("scenes", [])}
    return {}


def script_lines(script: str, support: dict[str, Any] | None,
                 claims: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The script beat by beat (D-69): each line with its kind (beat heading, on-screen note or
    spoken), the claims it cites (quote and source shown beside it) and the support-check flags
    (D-44) for its sentences."""
    flagged = [v for v in (support or {}).get("verdicts", []) if not v["supported"]]
    by_id = {c["id"]: c for c in claims or []}
    lines = []
    for text in script.strip().splitlines():
        if not text.strip():
            continue
        bare = script_checks.MARKER.sub("", text).strip()
        kind = ("beat" if text.startswith("##") else
                "screen" if text.lstrip().startswith("[ON SCREEN") else "spoken")
        cited = [by_id[f"C{n}"] for n in script_checks.MARKER.findall(text) if f"C{n}" in by_id]
        lines.append({"text": text, "bare": bare.lstrip("# ").strip("[]") if kind != "spoken"
                      else bare, "kind": kind, "claims": cited,
                      "flags": [v for v in flagged if v["sentence"][:60].strip() in bare]})
    return lines


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
    """A finished run: the video, one download per export file and the QA summary."""
    files = {name: key for (_, name), key in actions.latest_artifacts(s, project_id).items()}
    report = actions.read_latest(s, project_id, "qa_report.json")
    return {"video": files.get("video.mp4"), "thumbnail": files.get("thumbnail.png"),
            "downloads": [(label, files[name]) for name, label in DOWNLOADS.items()
                          if name in files],
            "qa_report": json.loads(report) if report else None}


def _technical(s: Any, project_id: str) -> dict[str, Any]:
    """For Technical details (D-63): the cost breakdown and the raw QA report."""
    costs = s.execute(select(Cost.provider, Cost.observed_or_estimate, func.count(),
                             func.sum(Cost.units), func.sum(Cost.amount))
                      .where(Cost.project_id == project_id)
                      .group_by(Cost.provider, Cost.observed_or_estimate)
                      .order_by(Cost.provider)).all()
    report = actions.read_latest(s, project_id, "qa_report.json")
    return {"costs": costs, "qa_report": json.loads(report) if report else None}


def _return_to(form: dict[str, str], default: str) -> str:
    """Where a form sends you back to: the planner or the library, else the run page."""
    back = form.get("back", "")
    return back if back.split("?")[0] in ("/planner", "/library") else default


def _video(project_id: str) -> dict[str, Any]:
    """This video's one status chip and actions, the same as its Library card (D-69)."""
    from app.ui import planner  # planner renders with this module's templates

    return planner.one(project_id)


GENERATING = [("voice", "Voice"), ("captions", "Captions"), ("render", "Render"),
              ("quality", "Quality check")]


def generating_step(run: dict[str, Any]) -> int:
    """Which Generating step is running (0-3); -1 while the shots are still being planned."""
    if run["status"] != "rendering":
        return -1
    key = f"{run['id']}/rendering/progress.json"
    store = storage.get()
    step = json.loads(store.read(key))["step"] if store.exists(key) else "voice"
    return [name for name, _ in GENERATING].index(step)


def _back(path: str, error: HTTPException) -> RedirectResponse:
    detail = error.detail if isinstance(error.detail, str) else "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg')}" for e in error.detail)
    return RedirectResponse(f"{path}?error={quote(detail)}", status_code=303)


def _schedule(project_id: str, status: str) -> dict[str, Any] | None:
    from app.ui import planner  # planner renders with this module's templates

    return planner.schedule(project_id, status)


templates.env.globals["generating"] = GENERATING
