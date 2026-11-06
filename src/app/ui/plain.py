"""Plain words for the product view (D-63): what a run is doing, the six-step progress bar, the QA
summary with ticks and the cost in rupees. The engineering names stay in Technical details."""

import re
from typing import Any

from app.core import config

# Run status -> what a person reads (D-69: one status per video, plain words).
STATUS = {
    "draft": "Writing script…",
    "researching": "Writing script…",
    "scripting": "Writing script…",
    "script_review": "Needs your review (script)",
    "storyboarding": "Generating…",
    "rendering": "Generating…",
    "qa_review": "Needs your review (video)",
    "approved": "Ready",
    "export_ready": "Ready",
    "mock_published": "Publishing…",
    "metrics_stub": "Publishing…",
    "done": "Published",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "research_review": "Waiting at a retired review step (cancel and restart)",
}
# The six steps a person sees, and the statuses (or failed stages) each covers.
STEPS = [
    ("Research & write", {"draft", "researching", "research_review", "scripting"}),
    ("Script review", {"script_review"}),
    ("Generate", {"storyboarding", "rendering"}),
    ("Final review", {"qa_review"}),
    ("Ready", {"approved", "export_ready"}),
    ("Published", {"mock_published", "metrics_stub", "done"}),
]
GATES = {"script_review": "Script review", "qa_review": "Final review"}
# Where a reject sends the run, in words.
TARGETS = {"researching": "Research — find new sources", "scripting": "Script — rewrite it",
           "storyboarding": "Visual plan — re-plan the shots", "rendering": "Video — render again"}


RAN = re.compile(r"would run (\d+(?:\.\d+)?)s|runtime (\d+)s|the Short runs (\d+(?:\.\d+)?)s")


def failure(message: str, asked: int | None, mode: str) -> str | None:
    """A run's failure in plain words, or None to show the raw step and error (D-71)."""
    ran = RAN.search(message)
    if ran and asked:
        seconds = round(float(next(g for g in ran.groups() if g)))
        what = "Video" if message.startswith("the Short runs") else "Script"
        if mode == "prototype":
            return (f"{what} came out at {seconds}s but you asked for {asked}s. In prototype "
                    "mode scripts can't be shortened — pick 60s, or wait for production mode.")
        return (f"{what} came out at {seconds}s but you asked for at most {asked}s, and the "
                "rewrites couldn't cut it enough. Retry, pick a longer length, or edit the "
                "last draft yourself.")
    if message.startswith("script failed checks"):
        return ("The script didn't pass its checks after its rewrites. Open it to fix the last "
                "draft yourself (every problem is marked), or Retry.")
    return None


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
            your_turn = run["status"] in GATES or run["status"] == "export_ready"  # D-64
            state = "turn" if your_turn else "active"
        steps.append({"name": name, "state": state})
    return steps


def qa_ticks(report: dict[str, Any] | None) -> list[tuple[bool, str]]:
    """The automated QA as ticks: length, loudness, pacing, captions; only the checks the report
    actually holds (a check it does not hold is never shown as passed or failed)."""
    if not report:
        return []
    ticks = []
    if "duration_s" in report:
        ticks.append((bool(report.get("duration_ok")), f"{report['duration_s']}s"))
    if "loudness_ok" in report:
        ticks.append((bool(report["loudness_ok"]), "loudness"))
    if "pacing" in report:
        ticks.append((bool(report["pacing"].get("ok")), "pacing"))
    if "cues" in report:
        ticks.append((bool(report["cues"]), "captions"))
    return ticks


def rupees(usd: float) -> str:
    """Recorded spend in rupees at the config rate (an approximate conversion)."""
    return f"₹{usd * float(config.load()['inr_per_usd']):,.2f}"
