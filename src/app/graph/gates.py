"""Human gates (D-05). Nothing runs before interrupt(): the node re-runs from the top on resume."""

from collections.abc import Callable
from typing import Any

from langgraph.types import Command, interrupt

from app.core import audit, db
from app.core.contracts import Decision
from app.core.log import bind_contextvars, log
from app.core.models import Approval
from app.graph.stages import NEXT_ON_APPROVE, from_stage_on
from app.graph.state import State


def gate_node(gate: str) -> Callable[..., Any]:
    def node(state: State) -> Command[str]:
        decision = Decision.model_validate(interrupt({"gate": gate}))
        project_id = state["project_id"]
        bind_contextvars(project_id=project_id, stage=gate, attempt=None)
        _record(project_id, gate, decision, state)
        if decision.decision == "approve":
            return Command(goto=NEXT_ON_APPROVE[gate])
        assert decision.target is not None  # Decision validator guarantees it
        notes = {decision.target: decision.notes}
        return Command(goto=decision.target, update={"review_notes": notes})

    return node


def _record(project_id: str, gate: str, decision: Decision, state: State) -> None:
    with db.session() as s, s.begin():
        if audit.decision_recorded(s, decision.decision_id):
            return  # replayed resume after a crash: already recorded
        reviewed = state["artifacts"].get(_reviewed_stage(gate), "")
        s.add(Approval(
            decision_id=decision.decision_id,
            project_id=project_id,
            stage=gate,
            approver=decision.reviewer,
            decision=decision.decision,
            target_stage=decision.target,
            notes=decision.notes,
            ai_disclosure=decision.ai_disclosure.model_dump() if decision.ai_disclosure else None,
            claim_edits={"removed": decision.removed_claims, "edited": decision.edited_claims}
            if gate == "research_review" else None,
            artifact_version=int(reviewed.rsplit("/v", 1)[1]) if reviewed else 0,
            opened_at=audit.gate_opened_at(s, project_id, gate),
            timestamp=decision.decided_at,
        ))
        if decision.decision == "approve" and gate == "qa_review":
            audit.transition(s, project_id, "approved", actor=decision.reviewer)
        elif decision.decision == "reject":
            assert decision.target is not None
            audit.mark_stale(s, project_id, from_stage_on(decision.target))
            audit.transition(s, project_id, decision.target, actor=decision.reviewer)
    log.info("gate decided", decision=decision.decision, target=decision.target,
             reviewer=decision.reviewer)


def _reviewed_stage(gate: str) -> str:
    return {"research_review": "researching", "script_review": "scripting",
            "qa_review": "rendering"}[gate]
