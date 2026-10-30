"""State-machine names from brief §05 (D-04) and the gate routing rules from ARCHITECTURE §3–§4."""

ORDER = [
    "draft",
    "researching",
    "research_review",
    "scripting",
    "script_review",
    "storyboarding",
    "rendering",
    "qa_review",
    "approved",
    "export_ready",
    "mock_published",
    "metrics_stub",
]
WORK = [s for s in ORDER if s not in ("research_review", "script_review", "qa_review", "approved")]

NEXT_ON_APPROVE = {
    "research_review": "scripting",
    "script_review": "storyboarding",
    "qa_review": "export_ready",
}
GATES = list(NEXT_ON_APPROVE)

REJECT_TARGETS = {
    "research_review": ["researching"],
    "script_review": ["researching", "scripting"],
    "qa_review": ["storyboarding", "rendering"],
}

# Status values outside ORDER.
DONE, FAILED, CANCELLED = "done", "failed", "cancelled"


def upstream(stage: str) -> list[str]:
    return [s for s in ORDER[: ORDER.index(stage)] if s in WORK]


def from_stage_on(stage: str) -> list[str]:
    return [s for s in ORDER[ORDER.index(stage) :] if s in WORK]
