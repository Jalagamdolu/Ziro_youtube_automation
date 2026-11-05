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
