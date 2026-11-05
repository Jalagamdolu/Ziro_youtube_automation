"""The planner (D-47, D-64): one row per video, Planned → Ready → Scheduled → Published. Planned
runs start 3 h before their time; a finished video publishes only in its slot and only if it was
approved before it. No login (D-61): every decision records Dolender."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

from conftest import DISCLOSURE, approve, create, status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import db
from app.core.models import AssetLicense, Topic
from app.jobs import reaper, scheduler
from app.ui import planner

TOPIC = "What makes an AI agent different from a chatbot?"  # has a prototype fixture
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64  # the header of a real MP4 file


def plan(client, hours_from_now: float | None, **extra: str) -> int:  # type: ignore[no-untyped-def]
    when = "" if hours_from_now is None else (datetime.now(UTC) + timedelta(
        hours=hours_from_now)).astimezone(planner.zone()).strftime("%Y-%m-%dT%H:%M")
    response = client.post("/planner", data={
        "topic": TOPIC, "format": "short", "publish_at": when,
        "guidelines": "Keep it practical."} | extra, follow_redirects=False)
    assert response.status_code == 303 and "error" not in response.headers["location"]
    with db.session() as s:
        return s.scalars(select(Topic.id).order_by(Topic.id.desc())).first()  # type: ignore[return-value]


def topic(topic_id: int) -> Topic:
    with db.session() as s:
        return s.get_one(Topic, topic_id)


def ready(client) -> str:  # type: ignore[no-untyped-def]
    """A video through both reviews: Ready, no slot yet."""
    project_id = create(client)
    approve(client, project_id)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert status(client, project_id)["status"] == "export_ready"
    return project_id


def slot(client, project_id: str, minutes: int, action: str = "") -> str:  # type: ignore[no-untyped-def]
    when = (datetime.now(UTC) + timedelta(minutes=minutes)).astimezone(planner.zone())
    response = client.post(f"/videos/{project_id}/schedule", data={
        "publish_at": when.strftime("%Y-%m-%dT%H:%M"), "action": action, "back": "/planner"},
        follow_redirects=False)
    return unquote(response.headers["location"])


def test_no_login_pages_open_and_decisions_record_dolender(client) -> None:
    from app.api.main import app

    anyone = TestClient(app)
    assert anyone.get("/planner", follow_redirects=False).status_code == 200
    assert anyone.get("/login").status_code == 404
    project_id = anyone.post("/projects", json={"prompt": TOPIC, "format": "short"}).json()["id"]
    assert approve(anyone, project_id, reviewer="someone else").status_code == 202
    assert status(anyone, project_id)["approvals"][0]["approver"] == "Dolender"


def test_a_planned_row_without_a_time_waits_for_make_now(client) -> None:
    topic_id = plan(client, None)
    page = client.get("/planner").text
    assert TOPIC in page and ">Planned<" in page and "Make now" in page and "No time yet" in page
    assert scheduler.start_due(datetime.now(UTC) + timedelta(days=30)) == []  # never by itself
    response = client.post(f"/planner/{topic_id}/run", follow_redirects=False)
    project_id = response.headers["location"].rsplit("/", 1)[1]
    assert topic(topic_id).project_id == project_id
    assert status(client, project_id)["status"] == "script_review"
    assert "Needs your review" in client.get("/planner").text  # same row, its next life stage


def test_a_planned_row_with_a_time_starts_three_hours_before(client) -> None:
    soon, later = plan(client, 2.5), plan(client, 5)
    page = client.get("/planner").text
    assert "Planned · starts" in page and "IST" in page and "Coming up" in page
    started = scheduler.start_due()
    assert len(started) == 1 and topic(soon).project_id == started[0]
    assert topic(later).status == "planned" and scheduler.start_due() == []


def test_a_finished_video_is_ready_and_pinned_until_it_gets_a_slot(client) -> None:
    project_id = ready(client)
    page = client.get("/planner").text
    assert page.index("Needs a slot") < page.index("Ready · needs a slot")
    assert "Schedule" in page and f"/videos/{project_id}/schedule" in page
    later = datetime.now(UTC) + timedelta(days=30)
    assert scheduler.publish_due(later) == []  # no slot, no publish
    assert project_id not in reaper.reap(later)  # parked, not stalled
    detail = client.get(f"/ui/projects/{project_id}").text
    assert "Ready — give it a publish time" in detail and "Approvals" in detail


def test_schedule_reschedule_unschedule_then_it_fires_in_its_slot(client) -> None:
    project_id = ready(client)
    assert "error" not in slot(client, project_id, 60)
    assert "Scheduled ·" in client.get("/planner").text
    assert "error" not in slot(client, project_id, 120)  # reschedule
    with db.session() as s:
        when = s.scalars(select(Topic.publish_at).where(Topic.project_id == project_id)).one()
    assert when is not None and when > datetime.now(UTC) + timedelta(minutes=110)
    assert "error" not in slot(client, project_id, 0, action="unschedule")
    assert "Ready · needs a slot" in client.get("/planner").text
    slot(client, project_id, 30)
    assert scheduler.publish_due() == []  # not yet
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=31)) == [project_id]
    run = status(client, project_id)
    assert run["status"] == "done"
    assert any(a["type"] == "publish_receipt.json" for a in run["artifacts"])
    assert ">Published (mock)<" in client.get("/planner").text


def test_no_final_approval_no_scheduling(client) -> None:
    project_id = create(client)  # waiting for the script review
    assert "only an approved video" in slot(client, project_id, 60)
    approve(client, project_id)  # script approved, final review still open
    assert "only an approved video" in slot(client, project_id, 60)
    assert "in the future" in slot(client, ready(client), -60)


def test_missed_slot_shows_red_and_never_publishes_until_rescheduled(client) -> None:
    plan(client, -1)  # its publish time already passed
    project_id = scheduler.start_due()[0]
    assert "Missed · waiting for your review" in client.get("/planner").text
    assert "Missed: the publish time" in client.get(f"/ui/projects/{project_id}").text
    approve(client, project_id)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert status(client, project_id)["status"] == "export_ready"
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(days=1)) == []  # approved too late
    page = client.get("/planner").text
    assert "Missed · needs a new time" in page and page.index("Needs a slot") < page.index(TOPIC)
    slot(client, project_id, 30)  # a new slot after the approval
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=31)) == [project_id]
    assert status(client, project_id)["status"] == "done"


def test_an_uploaded_recording_is_a_row_with_the_same_slots_and_lock(client) -> None:
    refused = client.post("/planner/upload", data={"title": "Sir on RAG"},
                          files={"video": ("rag.mp4", MP4, "video/mp4")}, follow_redirects=False)
    assert "tick the approval box" in unquote(refused.headers["location"])
    bad = client.post("/planner/upload", data={"title": "x", "approve": "yes"},
                      files={"video": ("x.mp4", b"not a video", "video/mp4")},
                      follow_redirects=False)
    assert "not an MP4" in unquote(bad.headers["location"])
    response = client.post("/planner/upload", data={"title": "Sir on RAG", "approve": "yes"},
                           files={"video": ("rag.mp4", MP4, "video/mp4")}, follow_redirects=False)
    project_id = response.headers["location"].rsplit("/", 1)[1]
    run = status(client, project_id)
    assert run["status"] == "export_ready"
    approval = run["approvals"][0]
    assert approval["stage"] == "qa_review" and approval["decision"] == "approve"
    assert approval["ai_disclosure"] == {"synthetic": False,
                                         "reason": "human content: uploaded recording"}
    with db.session() as s:
        assert s.scalars(select(AssetLicense).where(AssetLicense.project_id == project_id)).one()
    page = client.get("/planner").text
    assert "Sir on RAG" in page and "Uploaded" in page and "Ready · needs a slot" in page
    slot(client, project_id, 15)
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=16)) == [project_id]
    run = status(client, project_id)
    assert run["status"] == "done"
    receipt = next(a for a in run["artifacts"] if a["type"] == "publish_receipt.json")
    assert Path(receipt["storage_path"]).name == "publish_receipt.json"


def test_rows_show_real_length_cost_and_the_receipt_and_planned_rows_have_a_page(
        client, monkeypatch) -> None:
    import json

    import app.nodes as nodes
    from app.nodes import stubs

    def measured(ctx):  # type: ignore[no-untyped-def]
        return stubs.rendering(ctx) | {"qa_report.json": json.dumps({"duration_s": 37.0})}

    monkeypatch.setitem(nodes.FUNCS, "rendering", measured)
    topic_id = plan(client, None)
    page = client.get(f"/planner/{topic_id}").text
    assert "No time yet" in page and "Make now" in page
    project_id = ready(client)
    row = client.get("/planner").text
    assert "37.0 s · ₹0.00" in row  # its real length and cost, not "up to"
    slot(client, project_id, 10)
    scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=11))
    row = client.get("/planner").text
    assert ">Published (mock)<" in row and ">receipt</a>" in row
    client.post(f"/planner/{topic_id}/run")
    assert client.get(f"/planner/{topic_id}", follow_redirects=False).status_code == 303


def test_the_schedule_control_is_only_offered_after_the_final_approval(client) -> None:
    project_id = create(client)
    approve(client, project_id)  # at the final review
    assert f"/videos/{project_id}/schedule" not in client.get("/planner").text
    assert f"/videos/{project_id}/schedule" not in client.get(f"/ui/projects/{project_id}").text
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert f"/videos/{project_id}/schedule" in client.get("/planner").text


class WorkerKilled(BaseException):
    pass


def test_firing_is_idempotent_even_when_a_worker_dies_mid_publish(client, monkeypatch) -> None:
    import app.nodes as nodes
    from app.core.models import Publishing

    real, kills = nodes.FUNCS["mock_published"], iter([True])

    def dies_after_publishing(ctx):  # type: ignore[no-untyped-def]
        outputs = real(ctx)  # the mock publish row is written...
        if next(kills, False):
            raise WorkerKilled  # ...then the worker dies before the step is saved
        return outputs

    monkeypatch.setitem(nodes.FUNCS, "mock_published", dies_after_publishing)
    project_id = ready(client)
    slot(client, project_id, 10)
    due = datetime.now(UTC) + timedelta(minutes=11)
    assert scheduler.publish_due(due) == [project_id]
    assert scheduler.publish_due(due) == []  # the same slot never fires twice
    assert status(client, project_id)["status"] == "mock_published"  # stuck mid-publish
    assert reaper.reap(datetime.now(UTC) + timedelta(hours=1)) == [project_id]  # a restart
    assert status(client, project_id)["status"] == "done"
    with db.session() as s:
        assert len(s.scalars(select(Publishing).where(
            Publishing.project_id == project_id)).all()) == 1  # one publish, not two


# --- Row lifecycle (D-66): one chip per state, only that state's actions, two doorways ---------

BUTTONS = {"Make now": "/run\"", "Approve": "value=\"approve\"", "Reject": "value=\"reject\"",
           "Schedule": "/schedule\"", "Retry": "/retry\""}


def row(client, project_id: str) -> str:  # type: ignore[no-untyped-def]
    """The planner's row for one video."""
    page = client.get("/planner").text
    chunk = next(c for c in page.split('<div class="vrow')[1:] if project_id in c)
    return chunk.split("<h2")[0].split('<details class="panel" id=')[0]


def offered(html: str) -> set[str]:
    return {name for name, marker in BUTTONS.items() if marker in html}


def chips(html: str) -> int:
    return html.count('class="pill ') + html.count('class="pill"') - html.count(">Uploaded<")


def decide(client, project_id: str, **form: str) -> str:  # type: ignore[no-untyped-def]
    """A decision sent from the planner row (the second doorway)."""
    response = client.post(f"/ui/projects/{project_id}/decide",
                           data={"back": "/planner"} | form, follow_redirects=False)
    return unquote(response.headers["location"])


def test_each_state_shows_one_chip_and_only_its_actions(client) -> None:
    project_id = create(client)
    html = row(client, project_id)
    assert "Needs your review" in html and chips(html) == 1
    assert offered(html) == {"Approve", "Reject"} and "Read script" in html
    assert decide(client, project_id, decision="approve").startswith(
        f"/planner?submitted={project_id}:script_review")
    html = row(client, project_id)  # now at the final review: the disclosure comes with Approve
    assert "Needs your review" in html and offered(html) == {"Approve", "Reject"}
    assert 'name="ai_synthetic"' in html and "Watch" in html
    assert "/planner?submitted" in decide(client, project_id, decision="approve",
                                          ai_synthetic="yes", ai_reason="AI narration")
    html = row(client, project_id)
    assert "Ready · needs a slot" in html and chips(html) == 1 and offered(html) == {"Schedule"}
    slot(client, project_id, 3 * 24 * 60)
    html = row(client, project_id)
    assert "Scheduled ·" in html and "in 3 days" in html and "Unschedule" in html
    assert offered(html) == {"Schedule"} and chips(html) == 1  # Reschedule / Unschedule
    approvals = status(client, project_id)["approvals"]  # one approval system, two doorways
    assert [(a["stage"], a["decision"], a["approver"]) for a in approvals] == [
        ("script_review", "approve", "Dolender"), ("qa_review", "approve", "Dolender")]
    assert approvals[1]["ai_disclosure"] == {"synthetic": True, "reason": "AI narration"}


def test_a_decision_just_sent_shows_working_with_no_buttons(client) -> None:
    project_id = create(client)
    page = client.get(f"/planner?submitted={project_id}:script_review").text
    html = next(c for c in page.split('<div class="vrow')[1:] if project_id in c).split("<h2")[0]
    assert "Working on your decision…" in html and offered(html) == set()


def test_reject_from_the_planner_needs_a_note(client) -> None:
    project_id = create(client)
    refused = decide(client, project_id, decision="reject", target="scripting", notes="  ")
    assert refused.startswith("/planner?error=") and "notes" in refused
    run = status(client, project_id)
    assert run["status"] == "script_review" and run["approvals"] == []
    assert "/planner?submitted" in decide(client, project_id, decision="reject",
                                          target="scripting", notes="Shorter hook")
    rejection = status(client, project_id)["approvals"][0]
    assert (rejection["decision"], rejection["notes"]) == ("reject", "Shorter hook")
    assert "Needs your review" in row(client, project_id)  # rewritten, back at the review


def test_published_only_after_confirmation(client, monkeypatch) -> None:
    import app.nodes as nodes

    assert planner.confirmation(None) is None
    assert planner.confirmation({"video_id": "abc"}) is None  # sent is not published
    live = planner.confirmation({"confirmed_at": "Tue 10 Nov, 18:00 IST",
                                 "watch_url": "https://youtu.be/abc"})
    assert live is not None and live["label"] == "Live on YouTube"
    real, kills = nodes.FUNCS["mock_published"], iter([True])

    def dies_before_the_receipt(ctx):  # type: ignore[no-untyped-def]
        if next(kills, False):
            raise WorkerKilled  # the publish step is under way, nothing confirmed yet
        return real(ctx)

    monkeypatch.setitem(nodes.FUNCS, "mock_published", dies_before_the_receipt)
    project_id = ready(client)
    slot(client, project_id, 10)
    scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=11))
    html = row(client, project_id)
    assert "Publishing…" in html and "Published" not in html and offered(html) == set()
    reaper.reap(datetime.now(UTC) + timedelta(hours=1))
    html = row(client, project_id)
    assert "Published (mock)" in html and ">receipt</a>" in html and "IST" in html
    from sqlalchemy import update

    from app.core.models import Artifact
    with db.session() as s, s.begin():  # no receipt on record: not confirmed, not Published
        s.execute(update(Artifact).where(
            Artifact.project_id == project_id,
            Artifact.type == "publish_receipt.json").values(stale=True))
    html = row(client, project_id)
    assert "Publishing…" in html and "Published" not in html


def test_a_failed_video_says_why_in_red_and_offers_retry(client, monkeypatch) -> None:
    import app.nodes as nodes
    from app.core.errors import FatalError

    real, fails = nodes.FUNCS["scripting"], iter([True])

    def broken(ctx):  # type: ignore[no-untyped-def]
        if next(fails, False):
            raise FatalError("claim check failed: line 3 has no approved claim")
        return real(ctx)

    monkeypatch.setitem(nodes.FUNCS, "scripting", broken)
    project_id = create(client)
    html = row(client, project_id)
    assert "pill bad" in html and ">Failed<" in html and chips(html) == 1
    assert "line 3 has no approved claim" in html and offered(html) == {"Retry"}
    response = client.post(f"/ui/projects/{project_id}/retry", data={"back": "/planner"},
                           follow_redirects=False)
    assert response.headers["location"] == "/planner"
    assert "Needs your review" in row(client, project_id)
