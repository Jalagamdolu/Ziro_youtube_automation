"""HTTP API (§2, §7) and the review UI (§8). Endpoints only validate and enqueue."""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import actions
from app.api.actions import CreateRequest, DecisionRequest
from app.jobs import reaper
from app.ui import routes as ui


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    threading.Thread(target=reaper.run_forever, daemon=True).start()
    yield


app = FastAPI(title="Ziro YouTube Automation (sandbox)", lifespan=lifespan)
app.include_router(ui.router)
app.mount("/static", StaticFiles(directory=Path(ui.__file__).parent / "static"), name="static")


@app.post("/projects", status_code=201)
def create(request: CreateRequest) -> dict[str, str]:
    return {"id": actions.create_project(request)}


@app.get("/projects/{project_id}")
def status(project_id: str) -> dict[str, Any]:
    return actions.run_status(project_id)


@app.post("/projects/{project_id}/approve", status_code=202)
def approve(project_id: str, body: DecisionRequest) -> dict[str, str]:
    return {"decision_id": actions.decide(project_id, "approve", body)}


@app.post("/projects/{project_id}/reject", status_code=202)
def reject(project_id: str, body: DecisionRequest) -> dict[str, str]:
    return {"decision_id": actions.decide(project_id, "reject", body)}


@app.post("/projects/{project_id}/retry", status_code=202)
def retry(project_id: str) -> dict[str, str]:
    return {"job_id": actions.retry(project_id)}


@app.post("/projects/{project_id}/cancel")
def cancel(project_id: str) -> dict[str, str]:
    actions.cancel(project_id)
    return {"status": "cancelled"}
