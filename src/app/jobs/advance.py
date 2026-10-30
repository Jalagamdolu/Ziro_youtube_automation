"""The only way the graph runs (§7): an RQ job that advances one project to its next gate or END."""

from typing import Any

from langchain_core.runnables import RunnableConfig  # LangGraph's config type, not an LLM wrapper
from langgraph.types import Command

from app.core import audit, db
from app.core.log import bind_contextvars, clear_contextvars, log
from app.core.models import Project
from app.graph.build import build, checkpointer
from app.graph.stages import CANCELLED, DONE, FAILED


def advance(project_id: str, resume: dict[str, Any] | None = None) -> str:
    clear_contextvars()
    bind_contextvars(project_id=project_id)
    with db.session() as s:
        status = s.get_one(Project, project_id).status
    if status in (DONE, CANCELLED):
        log.info("advance skipped", status=status)
        return status

    thread: RunnableConfig = {"configurable": {"thread_id": project_id}}
    with checkpointer() as saver:
        graph = build(saver)
        if resume is not None:
            start: Any = Command(resume=resume)
        elif graph.get_state(thread).values:
            start = None  # continue from the last checkpoint (retry, reaper)
        else:
            start = {"project_id": project_id, "artifacts": {}, "review_notes": {},
                     "status": "draft"}
        try:
            graph.invoke(start, thread, durability="sync")
        except Exception as error:
            with db.session() as s, s.begin():
                audit.transition(s, project_id, FAILED)
            log.error("run failed", error_code=type(error).__name__, error=str(error))
            return FAILED
        snapshot = graph.get_state(thread)

    with db.session() as s, s.begin():
        if snapshot.interrupts:
            audit.transition(s, project_id, snapshot.interrupts[0].value["gate"])
        elif not snapshot.next:
            audit.transition(s, project_id, DONE)
        status = s.get_one(Project, project_id).status
    log.info("advance stopped", status=status)
    return status
