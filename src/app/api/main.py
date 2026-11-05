"""HTTP API (§2, §7) and the review UI (§8). Endpoints only validate and enqueue."""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api import actions
from app.api.actions import CreateRequest, DecisionRequest
from app.core import engines
from app.core.log import log
from app.jobs import reaper, scheduler
from app.ui import auth, planner
from app.ui import routes as ui


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Which engines run and which keys are present (names only), so a missing key is plain to
    # see; keys upgrade quality, never block (D-46).
    found = engines.status()
    log.info("engines", mode=found["mode"], writer=found["writer"], voice=found["voice"],
             present=[n for n, ok in found["keys"].items() if ok],  # names only, never values
             missing=[n for n, ok in found["keys"].items() if not ok])
    for line in engines.banners():
        log.warning("engine fallback", detail=line)
    threading.Thread(target=reaper.run_forever, daemon=True).start()
    jobs = scheduler.start()
    yield
    jobs.shutdown(wait=False)


app = FastAPI(title="Ziro AI Content Studio (sandbox)", lifespan=lifespan)
app.middleware("http")(auth.middleware)
app.include_router(ui.router)
app.include_router(planner.router)
app.mount("/static", StaticFiles(directory=Path(ui.__file__).parent / "static"), name="static")


@app.post("/projects", status_code=201)
def create(request: CreateRequest) -> dict[str, str]:
    return {"id": actions.create_project(request)}


@app.get("/projects/{project_id}")
def status(project_id: str) -> dict[str, Any]:
    return actions.run_status(project_id)


@app.post("/projects/{project_id}/approve", status_code=202)
def approve(project_id: str, body: DecisionRequest, request: Request) -> dict[str, str]:
    body.reviewer = request.state.user["name"]  # decisions record who is logged in (D-47)
    return {"decision_id": actions.decide(project_id, "approve", body)}


@app.post("/projects/{project_id}/reject", status_code=202)
def reject(project_id: str, body: DecisionRequest, request: Request) -> dict[str, str]:
    body.reviewer = request.state.user["name"]
    return {"decision_id": actions.decide(project_id, "reject", body)}


@app.post("/projects/{project_id}/retry", status_code=202)
def retry(project_id: str) -> dict[str, str]:
    return {"job_id": actions.retry(project_id)}


@app.post("/projects/{project_id}/cancel")
def cancel(project_id: str) -> dict[str, str]:
    actions.cancel(project_id)
    return {"status": "cancelled"}
