"""The product view's words (D-63): plain statuses, the six-step progress bar, QA ticks, rupees."""

from app.ui import plain


def run(status: str, failed_stage: str | None = None) -> dict:  # type: ignore[type-arg]
    jobs = [{"stage": failed_stage, "status": "failed"}] if failed_stage else []
    return {"status": status, "jobs": jobs, "events": []}


def states(status: str, failed_stage: str | None = None) -> list[str]:
    return [s["state"] for s in plain.stepper(run(status, failed_stage))]


def test_the_stepper_follows_the_run() -> None:
    assert [s["name"] for s in plain.stepper(run("draft"))] == [
        "Research", "Script", "Your review", "Render", "Your review", "Published"]
    assert states("researching") == ["active", "todo", "todo", "todo", "todo", "todo"]
    assert states("script_review") == ["done", "done", "turn", "todo", "todo", "todo"]
    assert states("rendering") == ["done", "done", "done", "active", "todo", "todo"]
    assert states("qa_review") == ["done", "done", "done", "done", "turn", "todo"]
    assert states("done") == ["done"] * 6
    assert states("failed", "scripting") == ["done", "failed", "todo", "todo", "todo", "todo"]


def test_statuses_are_plain_words_without_stage_names() -> None:
    assert plain.status("scripting") == "Writing the script…"
    assert plain.status("qa_review") == "Waiting for your final review"
    assert all("_" not in plain.status(s) for s in plain.STATUS)


def test_qa_becomes_ticks() -> None:
    report = {"duration_s": 39.2, "duration_ok": True, "loudness_ok": True,
              "pacing": {"ok": False}, "cues": 12}
    assert plain.qa_ticks(report) == [(True, "39.2s"), (True, "loudness"), (False, "pacing"),
                                      (True, "captions")]


def test_cost_is_shown_in_rupees() -> None:
    assert plain.rupees(0.5).startswith("₹") and plain.rupees(0) == "₹0.00"
