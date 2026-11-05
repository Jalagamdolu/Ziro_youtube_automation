"""Plain words for the product view (D-63): what a run is doing, the six-step progress bar, the QA
summary with ticks and the cost in rupees. The engineering names stay in Technical details."""

from typing import Any

from app.core import config

# Run status -> what a person reads.
STATUS = {
    "draft": "Getting started…",
    "researching": "Researching sources…",
    "scripting": "Writing the script…",
    "script_review": "Waiting for your script review",
    "storyboarding": "Planning the visuals…",
    "rendering": "Rendering the video…",
    "qa_review": "Waiting for your final review",
    "approved": "Approved — publishing…",
    "export_ready": "Approved — waiting for its publish time",
    "mock_published": "Publishing…",
    "metrics_stub": "Publishing…",
    "done": "Published (mock)",
    "failed": "Stopped — needs your attention",
    "cancelled": "Cancelled",
    "research_review": "Waiting at a retired review step (cancel and restart)",
}
# The six steps a person sees, and the statuses (or failed stages) each covers.
STEPS = [
    ("Research", {"draft", "researching", "research_review"}),
    ("Script", {"scripting"}),
    ("Your review", {"script_review"}),
    ("Render", {"storyboarding", "rendering"}),
    ("Your review", {"qa_review"}),
    ("Published", {"approved", "export_ready", "mock_published", "metrics_stub", "done"}),
]
GATES = {"script_review": "Script review", "qa_review": "Final review"}
# Where a reject sends the run, in words.
TARGETS = {"researching": "Research — find new sources", "scripting": "Script — rewrite it",
           "storyboarding": "Visual plan — re-plan the shots", "rendering": "Video — render again"}


def status(value: str) -> str:
    return STATUS.get(value, value.replace("_", " "))


def tone(value: str) -> str:
    """Pill colour: green done, amber your turn, red stopped, plain otherwise."""
    return ("ok" if value == "done" else "warn" if value in GATES or value == "export_ready"
            else "bad" if value == "failed" else "")


def stepper(run: dict[str, Any]) -> list[dict[str, str]]:
    """[{name, state}] with state done / active / turn (your review) / failed / todo."""
    current = run["status"]
    if current == "failed":
        failed = [j["stage"] for j in run["jobs"] if j["status"] == "failed"]
        current = failed[-1] if failed else "draft"
    elif current == "cancelled":
        current = next((e["from_state"] for e in reversed(run["events"])
                        if e["to_state"] == "cancelled"), "draft") or "draft"
    at = next((i for i, (_, covers) in enumerate(STEPS) if current in covers), 0)
    steps = []
    for i, (name, _) in enumerate(STEPS):
        if run["status"] == "done" or i < at:
            state = "done"
        elif i > at:
            state = "todo"
        elif run["status"] == "failed":
            state = "failed"
        elif run["status"] == "cancelled":
            state = "todo"
        else:
            state = "turn" if run["status"] in GATES else "active"
        steps.append({"name": name, "state": state})
    return steps


def qa_ticks(report: dict[str, Any] | None) -> list[tuple[bool, str]]:
    """The automated QA as ticks: length, loudness, pacing, captions."""
    if not report:
        return []
    return [(bool(report.get("duration_ok")), f"{report.get('duration_s')}s"),
            (bool(report.get("loudness_ok", True)), "loudness"),
            (bool(report.get("pacing", {}).get("ok", True)), "pacing"),
            (bool(report.get("cues")), "captions")]


def rupees(usd: float) -> str:
    """Recorded spend in rupees at the config rate (an approximate conversion)."""
    return f"₹{usd * float(config.load()['inr_per_usd']):,.2f}"
