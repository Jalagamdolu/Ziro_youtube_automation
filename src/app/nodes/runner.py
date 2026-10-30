"""Node contract (§4) for every work stage: audit rows, input-hash cache, versioned outputs."""

import hashlib
import json
from typing import Any

from sqlalchemy import update

import app.nodes as nodes
from app.adapters import storage
from app.core import audit, db
from app.core.log import bind_contextvars, log
from app.core.models import Artifact
from app.graph.stages import upstream
from app.graph.state import State
from app.nodes.context import StageContext

HASH_FILE = ".input_hash"


def run_stage(stage: str, state: State) -> dict[str, Any]:
    project_id = state["project_id"]
    with db.session() as s, s.begin():
        audit.transition(s, project_id, stage)
        job = audit.start_job(s, project_id, stage)
    bind_contextvars(project_id=project_id, stage=stage, attempt=job.retry_count + 1)

    inputs = {u: state["artifacts"][u] for u in upstream(stage) if u in state["artifacts"]}
    notes = state["review_notes"].get(stage)
    input_hash = _hash(stage, inputs, notes)
    store = storage.get()

    with db.session() as s, s.begin():
        latest = audit.latest_version(s, project_id, stage)
    cached = _find_cached(store, project_id, stage, latest, input_hash)
    if cached is not None:
        with db.session() as s, s.begin():
            s.execute(update(Artifact).where(Artifact.storage_path.startswith(cached + "/"))
                      .values(stale=False))
            audit.finish_job(s, job.id, "cached")
        log.info("stage cached", prefix=cached)
        return {"artifacts": {stage: cached}, "status": stage}

    log.info("stage started")
    try:
        outputs = nodes.FUNCS[stage](StageContext(project_id, inputs, notes, store))
    except Exception as error:
        with db.session() as s, s.begin():
            audit.finish_job(s, job.id, "failed", error)
        log.warning("stage failed", error_code=type(error).__name__, error=str(error))
        raise

    prefix = f"{project_id}/{stage}/v{latest + 1}"
    with db.session() as s, s.begin():
        for name, content in outputs.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            s.add(Artifact(
                project_id=project_id, stage=stage, type=name, version=latest + 1,
                storage_path=store.write(f"{prefix}/{name}", data),
                checksum=hashlib.sha256(data).hexdigest(), model_or_tool="stub",
            ))
        store.write(f"{prefix}/{HASH_FILE}", input_hash.encode())
        audit.finish_job(s, job.id, "succeeded")
    log.info("stage succeeded", prefix=prefix)
    return {"artifacts": {stage: prefix}, "status": stage}


def _hash(stage: str, inputs: dict[str, str], notes: str | None) -> str:
    # Upstream prefixes are immutable versions, so they identify their content.
    key = json.dumps({"stage": stage, "inputs": inputs, "notes": notes}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()


def _find_cached(
    store: storage.Storage, project_id: str, stage: str, latest: int, input_hash: str
) -> str | None:
    for version in range(latest, 0, -1):
        prefix = f"{project_id}/{stage}/v{version}"
        key = f"{prefix}/{HASH_FILE}"
        if store.exists(key) and store.read(key).decode() == input_hash:
            return prefix
    return None
