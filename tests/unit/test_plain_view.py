"""The product view's words (D-63): plain statuses, the six-step progress bar, QA ticks, rupees."""

from app.ui import plain


def run(status: str, failed_stage: str | None = None) -> dict:  # type: ignore[type-arg]
    jobs = [{"stage": failed_stage, "status": "failed"}] if failed_stage else []
    return {"status": status, "jobs": jobs, "events": []}


def states(status: str, failed_stage: str | None = None) -> list[str]:
    return [s["state"] for s in plain.stepper(run(status, failed_stage))]


def test_the_stepper_follows_the_run() -> None:
    assert [s["name"] for s in plain.stepper(run("draft"))] == [
        "Research & write", "Script review", "Generate", "Final review", "Ready", "Published"]
    assert states("researching") == ["active", "todo", "todo", "todo", "todo", "todo"]
    assert states("script_review") == ["done", "turn", "todo", "todo", "todo", "todo"]
    assert states("rendering") == ["done", "done", "active", "todo", "todo", "todo"]
    assert states("qa_review") == ["done", "done", "done", "turn", "todo", "todo"]
    assert states("export_ready") == ["done", "done", "done", "done", "turn", "todo"]
    assert states("done") == ["done"] * 6
    assert states("failed", "scripting") == ["failed", "todo", "todo", "todo", "todo", "todo"]


def test_statuses_are_plain_words_without_stage_names() -> None:
    assert plain.status("scripting") == "Writing script…"  # D-69's words
    assert plain.status("script_review") == "Needs your review (script)"
    assert plain.status("rendering") == "Generating…"
    assert plain.status("qa_review") == "Needs your review (video)"
    assert all("_" not in plain.status(s) for s in plain.STATUS)


def test_qa_becomes_ticks() -> None:
    report = {"duration_s": 39.2, "duration_ok": True, "loudness_ok": True,
              "pacing": {"ok": False}, "cues": 12}
    assert plain.qa_ticks(report) == [(True, "39.2s"), (True, "loudness"), (False, "pacing"),
                                      (True, "captions")]
    assert plain.qa_ticks({"stub": True}) == []  # nothing measured, nothing claimed


def test_failures_are_plain_words() -> None:
    script = ("script failed checks after 0 revisions: with its pauses the Short would run "
              "52.3s; it was asked for at most 30s: cut about 68 spoken words in the Example "
              "section")
    assert plain.failure(script, 30, "prototype") == (
        "Script came out at 52s but you asked for 30s. In prototype mode scripts can't be "
        "shortened — pick 60s, or wait for production mode.")
    assert "rewrites couldn't cut it" in (plain.failure(script, 30, "production") or "")
    video = "the Short runs 41.6s but was asked for at most 40s, even with the pauses tightened."
    assert (plain.failure(video, 40, "production") or "").startswith("Video came out at 42s")
    other = "script failed checks after 2 revisions: the five hooks must be distinct"
    assert "every problem is marked" in (plain.failure(other, 60, "production") or "")
    assert plain.failure("claim check failed: line 3", 60, "production") is None


def test_cost_is_shown_in_rupees() -> None:
    assert plain.rupees(0.5).startswith("₹") and plain.rupees(0) == "₹0.00"
