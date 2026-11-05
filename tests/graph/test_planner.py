"""Topic planner and scheduler (D-47): planned runs start 3 h early, publish at their time and
never before both reviews. No login (D-61): every decision records Dolender."""

from datetime import UTC, datetime, timedelta

from conftest import DISCLOSURE, approve, status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import db
from app.core.models import Topic
from app.jobs import reaper, scheduler
from app.ui import planner

TOPIC = "What makes an AI agent different from a chatbot?"  # has a prototype fixture


def plan(client, hours_from_now: float, **extra: str) -> int:  # type: ignore[no-untyped-def]
    when = (datetime.now(UTC) + timedelta(hours=hours_from_now)).astimezone(planner.zone())
    response = client.post("/planner", data={
        "topic": TOPIC, "format": "short", "publish_at": when.strftime("%Y-%m-%dT%H:%M"),
        "keywords": "agents, chatbots", "guidelines": "Keep it practical."} | extra,
        follow_redirects=False)
    assert response.status_code == 303 and "error" not in response.headers["location"]
    with db.session() as s:
        return s.scalars(select(Topic.id).order_by(Topic.id.desc())).first()  # type: ignore[return-value]


def topic(topic_id: int) -> Topic:
    with db.session() as s:
        return s.get_one(Topic, topic_id)


def test_no_login_pages_open_and_decisions_record_dolender(client) -> None:
    from app.api.main import app

    anyone = TestClient(app)
    assert anyone.get("/planner", follow_redirects=False).status_code == 200
    assert anyone.get("/login").status_code == 404
    project_id = anyone.post("/projects", json={"prompt": TOPIC, "format": "short"}).json()["id"]
    assert approve(anyone, project_id, reviewer="someone else").status_code == 202
    assert status(anyone, project_id)["approvals"][0]["approver"] == "Dolender"


def test_planned_topic_lists_its_start_time_and_runs_now_with_its_guidance(client) -> None:
    topic_id = plan(client, 24)
    page = client.get("/planner").text
    assert TOPIC in page and "Planned · starts" in page and "IST" in page
    assert "agents, chatbots" in page
    response = client.post(f"/planner/{topic_id}/run", follow_redirects=False)
    project_id = response.headers["location"].rsplit("/", 1)[1]
    assert topic(topic_id).status == "started" and topic(topic_id).project_id == project_id
    run = status(client, project_id)
    assert run["status"] == "script_review" and run["events"][0]["actor"] == "Dolender"
    assert client.post(f"/planner/{topic_id}/run", follow_redirects=False
                       ).headers["location"].startswith("/planner?error")  # once only


def test_scheduler_starts_runs_three_hours_before_publish(client) -> None:
    soon, later = plan(client, 2.5), plan(client, 5)
    started = scheduler.start_due()
    assert len(started) == 1 and topic(soon).project_id == started[0]
    assert topic(later).status == "planned"
    assert scheduler.start_due() == []  # never twice
    assert scheduler.start_due(datetime.now(UTC) + timedelta(hours=2.5)) == [
        topic(later).project_id]


def test_approved_run_waits_for_its_publish_time_then_publishes(client) -> None:
    topic_id = plan(client, 2)
    project_id = scheduler.start_due()[0]
    approve(client, project_id)  # script_review
    approve(client, project_id, ai_disclosure=DISCLOSURE)  # qa_review
    run = status(client, project_id)
    assert run["status"] == "export_ready"  # approved, parked until publish_at
    assert not any(a["type"] == "publish_receipt.json" for a in run["artifacts"])
    assert project_id not in reaper.reap(datetime.now(UTC) + timedelta(minutes=90))
    assert "Approved · publishes" in client.get("/planner").text
    assert "Publishes (mock) at" in client.get(f"/ui/projects/{project_id}").text

    assert scheduler.publish_due() == []  # not yet
    when = topic(topic_id).publish_at
    assert scheduler.publish_due(when + timedelta(minutes=1)) == [project_id]
    run = status(client, project_id)
    assert run["status"] == "done"
    assert any(a["type"] == "publish_receipt.json" for a in run["artifacts"])
    assert "Published (mock)" in client.get("/planner").text


def test_missed_publish_time_is_said_and_nothing_publishes_before_review(client) -> None:
    topic_id = plan(client, -1)  # publish time already passed
    project_id = scheduler.start_due()[0]
    assert status(client, project_id)["status"] == "script_review"
    assert "MISSED publish time · nothing published" in client.get("/planner").text
    assert "has passed — nothing was published" in client.get(f"/ui/projects/{project_id}").text
    assert scheduler.publish_due() == []  # not approved: the scheduler never pushes it
    approve(client, project_id)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert status(client, project_id)["status"] == "done"  # approved late: publishes at once
    assert topic(topic_id).status == "started"
