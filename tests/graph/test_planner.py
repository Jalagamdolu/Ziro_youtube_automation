"""Library and Planner (D-64, D-66, D-69): one status chip per video and only that state's
actions; Ready → Publish now or Schedule; the Planner is the calendar. Planned topics start 3 h
before their time; a finished video publishes only after the final approval, and shows as
Published only once that publish is confirmed. No login (D-61): every action records Dolender."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

from conftest import DISCLOSURE, approve, create, status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import db
from app.core.models import AssetLicense, Event, Publishing, Topic
from app.jobs import reaper, scheduler
from app.ui import planner

TOPIC = "What makes an AI agent different from a chatbot?"  # has a prototype fixture
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64  # the header of a real MP4 file
BUTTONS = {"Make now": "/run\"", "Review now": ">Review now<", "Retry": "/retry\"",
           "Publish": "/publish-now\"", "Schedule": "/schedule\"", "Edit": "/metadata\"",
           "Preview": ">Preview<"}


def plan(client, hours_from_now: float | None, **extra: str) -> int:  # type: ignore[no-untyped-def]
    when = "" if hours_from_now is None else (datetime.now(UTC) + timedelta(
        hours=hours_from_now)).astimezone(planner.zone()).strftime("%Y-%m-%dT%H:%M")
    response = client.post("/planner", data={
        "topic": TOPIC, "publish_at": when, "guidelines": "Keep it practical."} | extra,
        follow_redirects=False)
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
        "publish_at": when.strftime("%Y-%m-%dT%H:%M"), "action": action, "back": "/library"},
        follow_redirects=False)
    return unquote(response.headers["location"])


def card(client, project_id: str) -> str:  # type: ignore[no-untyped-def]
    """The Library's card for one video."""
    page = client.get("/library").text
    chunk = next(c for c in page.split("<article")[1:] if project_id in c)
    return chunk.split("</article>")[0]


def offered(html: str) -> set[str]:
    return {name for name, marker in BUTTONS.items() if marker in html}


def chips(html: str) -> int:
    return html.count('class="pill ') - html.count('class="pill ok">mechanism')


def notes(project_id: str) -> list[tuple[str, str]]:
    with db.session() as s:
        return [(e.actor, e.note or "") for e in s.scalars(select(Event).where(
            Event.project_id == project_id, Event.note.is_not(None)).order_by(Event.id))]


def test_no_login_pages_open_and_decisions_record_dolender(client) -> None:
    from app.api.main import app

    anyone = TestClient(app)
    for page in ("/library", "/planner", "/new"):
        assert anyone.get(page, follow_redirects=False).status_code == 200
    assert anyone.get("/login").status_code == 404
    project_id = anyone.post("/projects", json={"prompt": TOPIC, "format": "short"}).json()["id"]
    assert approve(anyone, project_id, reviewer="someone else").status_code == 202
    assert status(anyone, project_id)["approvals"][0]["approver"] == "Dolender"


def test_each_state_shows_one_chip_and_only_its_actions(client) -> None:
    project_id = create(client)
    html = card(client, project_id)
    assert "Needs your review (script)" in html and chips(html) == 1
    assert offered(html) == {"Review now"}
    approve(client, project_id)
    html = card(client, project_id)
    assert "Needs your review (video)" in html and offered(html) == {"Review now"}
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    html = card(client, project_id)
    assert ">Ready<" in html and chips(html) == 1
    assert offered(html) == {"Publish", "Schedule", "Edit", "Preview"}
    assert ">Publish now<" in html and ">Download<" in html
    slot(client, project_id, 3 * 24 * 60)
    html = card(client, project_id)
    assert "Scheduled ·" in html and "in 3 days" in html and chips(html) == 1
    assert offered(html) == {"Publish", "Schedule", "Edit", "Preview"}
    assert ">Reschedule<" in html and ">Unschedule<" in html and ">Publish early<" in html


def test_needs_you_is_pinned_and_counted_and_filters_narrow_the_library(client) -> None:
    done = ready(client)
    waiting = create(client)  # newer, but the order is "needs you" first anyway
    page = client.get("/library").text
    assert page.index(waiting) < page.index(done) and "Needs you · 1" in page
    assert waiting in client.get("/library?show=needs").text
    assert done not in client.get("/library?show=needs").text
    assert done in client.get("/library?show=ready").text
    assert waiting not in client.get("/library?show=published").text


def test_final_approval_lands_in_the_library_with_a_toast(client) -> None:
    project_id = create(client)
    approve(client, project_id)
    response = client.post(f"/ui/projects/{project_id}/decide", data={
        "decision": "approve", "ai_synthetic": "yes", "ai_reason": "AI narration"},
        follow_redirects=False)
    assert response.headers["location"] == f"/library?saved={project_id}"
    page = client.get(response.headers["location"]).text
    assert "Saved to Library" in page and ">Ready<" in card(client, project_id)


def test_regenerate_needs_no_notes_and_rewrites_the_script(client) -> None:
    project_id = create(client)
    client.post(f"/ui/projects/{project_id}/decide", data={"decision": "regenerate"})
    run = status(client, project_id)
    rejection = run["approvals"][0]
    assert (rejection["decision"], rejection["target_stage"]) == ("reject", "scripting")
    assert rejection["notes"] == "Regenerate the script (no notes given)."
    assert run["status"] == "script_review"  # rewritten, back for review
    client.post(f"/ui/projects/{project_id}/decide", data={
        "decision": "regenerate", "target": "researching", "notes": "Find newer sources"})
    again = status(client, project_id)["approvals"][1]
    assert (again["target_stage"], again["notes"]) == ("researching", "Find newer sources")


def test_new_video_takes_a_preset_or_a_custom_length_of_at_most_sixty(client,
                                                                      monkeypatch) -> None:
    from app.api import actions

    page = client.get("/new").text
    assert 'name="keywords"' not in page and 'name="guidelines"' not in page  # D-71
    assert 'name="custom_seconds"' in page and 'value="60" checked' in page
    assert "Only 60s is available in prototype mode" in page

    def post(**form: str) -> str:
        response = client.post("/ui/projects", data={"prompt": TOPIC} | form,
                               follow_redirects=False)
        return unquote(response.headers["location"])

    assert "15 to 60" in post(length="custom", custom_seconds="70")  # the hard ceiling
    assert "15 to 60" in post(length="custom", custom_seconds="42.5")  # whole seconds
    assert "15 to 60" in post(length="custom", custom_seconds="10")
    assert "can't be shortened" in post(length="40")  # prototype: fixtures are fixed text
    made = post(length="60")
    assert status(client, made.rsplit("/", 1)[1])["brief"]["target_seconds"] == 60
    seen: list[actions.CreateRequest] = []
    monkeypatch.setattr(actions, "create_project", lambda request: seen.append(request) or "x")
    post(length="custom", custom_seconds="42", format="long", keywords="#agents, chatbots")
    assert (seen[0].target_seconds, seen[0].format) == (42, "short")  # a ceiling, Shorts only
    assert seen[0].keywords == ["agents", "chatbots"]  # the API still takes keywords


def test_a_planned_row_without_a_time_waits_for_make_now(client) -> None:
    topic_id = plan(client, None)
    assert "Make now" in client.get(f"/planner/{topic_id}").text
    assert scheduler.start_due(datetime.now(UTC) + timedelta(days=30)) == []  # never by itself
    response = client.post(f"/planner/{topic_id}/run", follow_redirects=False)
    project_id = response.headers["location"].rsplit("/", 1)[1]
    assert topic(topic_id).project_id == project_id
    assert status(client, project_id)["status"] == "script_review"
    assert "Needs your review (script)" in card(client, project_id)


def test_a_planned_row_with_a_time_starts_three_hours_before(client) -> None:
    soon, later = plan(client, 2.5), plan(client, 5)
    page = client.get("/planner?view=list").text
    assert "Planned · starts" in page and "IST" in page and "Coming up" in page
    started = scheduler.start_due()
    assert len(started) == 1 and topic(soon).project_id == started[0]
    assert topic(later).status == "planned" and scheduler.start_due() == []


def test_the_planner_is_a_month_calendar_and_a_list(client) -> None:
    project_id = ready(client)
    slot(client, project_id, 60)
    month = client.get("/planner").text
    assert 'class="cal-grid"' in month and f"/ui/projects/{project_id}" in month
    assert "upload as private until YouTube's audit" in month  # the banner
    listed = client.get("/planner?view=list").text
    assert "Scheduled ·" in listed and ">Unschedule<" in listed


def test_a_ready_video_waits_for_publish_now_or_a_slot(client) -> None:
    project_id = ready(client)
    later = datetime.now(UTC) + timedelta(days=30)
    assert scheduler.publish_due(later) == []  # no slot, no publish
    assert project_id not in reaper.reap(later)  # parked, not stalled
    assert "Ready — publish now or pick a time" in client.get(f"/ui/projects/{project_id}").text


def test_publish_now_publishes_at_once_under_the_same_lock(client) -> None:
    project_id = ready(client)
    response = client.post(f"/videos/{project_id}/publish-now", data={"back": "/library"},
                           follow_redirects=False)
    assert response.headers["location"] == "/library"
    assert status(client, project_id)["status"] == "done"
    html = card(client, project_id)
    assert ">Published (mock)<" in html and ">receipt</a>" in html and offered(html) == {
        "Preview"}
    again = client.post(f"/videos/{project_id}/publish-now", data={"back": "/library"},
                        follow_redirects=False)
    assert "not yet published" in unquote(again.headers["location"])  # never twice
    with db.session() as s:
        assert len(s.scalars(select(Publishing).where(
            Publishing.project_id == project_id)).all()) == 1
    assert ("Dolender", "publish now") in notes(project_id)  # who + when + what


def test_no_final_approval_no_publish_and_no_schedule(client) -> None:
    project_id = create(client)  # waiting for the script review
    assert "only an approved video" in slot(client, project_id, 60)
    approve(client, project_id)  # script approved, final review still open
    assert "only an approved video" in slot(client, project_id, 60)
    refused = client.post(f"/videos/{project_id}/publish-now", data={"back": "/library"},
                          follow_redirects=False)
    assert "only an approved video" in unquote(refused.headers["location"])
    assert f"/videos/{project_id}/publish-now" not in client.get("/library").text
    assert "in the future" in slot(client, ready(client), -60)


def test_schedule_reschedule_unschedule_then_it_fires_in_its_slot(client) -> None:
    project_id = ready(client)
    assert "error" not in slot(client, project_id, 60)
    assert "error" not in slot(client, project_id, 120)  # reschedule
    with db.session() as s:
        when = s.scalars(select(Topic.publish_at).where(Topic.project_id == project_id)).one()
    assert when is not None and when > datetime.now(UTC) + timedelta(minutes=110)
    assert "error" not in slot(client, project_id, 0, action="unschedule")
    assert ">Ready<" in card(client, project_id)
    slot(client, project_id, 30)
    assert scheduler.publish_due() == []  # not yet
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=31)) == [project_id]
    assert status(client, project_id)["status"] == "done"
    assert ">Published (mock)<" in card(client, project_id)
    actions = [note.split(" for ")[0] for _, note in notes(project_id)]
    assert actions == ["scheduled", "scheduled", "unscheduled", "scheduled"]


def test_a_missed_slot_shows_red_and_never_publishes_until_rescheduled(client) -> None:
    plan(client, -1)  # its publish time already passed
    project_id = scheduler.start_due()[0]
    assert "missed its slot" in card(client, project_id)
    approve(client, project_id)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(days=1)) == []  # approved late
    assert "Ready · missed its slot, pick a new time" in card(client, project_id)
    slot(client, project_id, 30)  # a new slot after the approval
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=31)) == [project_id]
    assert status(client, project_id)["status"] == "done"


def test_title_description_and_hashtags_are_edited_before_the_upload(client) -> None:
    project_id = ready(client)
    client.post(f"/videos/{project_id}/metadata", data={
        "title": "Chatbot or agent? The 10-second test", "description": "Two lines.",
        "hashtags": "#agents, #chatbots ai", "back": "/library"})
    assert "Chatbot or agent? The 10-second test" in card(client, project_id)
    client.post(f"/videos/{project_id}/publish-now", data={"back": "/library"})
    run = status(client, project_id)
    receipt = next(a for a in run["artifacts"] if a["type"] == "publish_receipt.json")
    import json

    from app.adapters import storage
    sent = json.loads(storage.get().read(receipt["storage_path"]))["request"]
    assert sent["snippet"]["title"] == "Chatbot or agent? The 10-second test"
    assert sent["snippet"]["tags"] == ["agents", "chatbots", "ai"]
    assert sent["snippet"]["description"].startswith("Two lines.\n\nAI disclosure:")
    assert sent["status"]["containsSyntheticMedia"] is True
    late = client.post(f"/videos/{project_id}/metadata", data={"title": "x", "back": "/library"},
                       follow_redirects=False)
    assert "not uploaded yet" in unquote(late.headers["location"])  # locked once published
    assert any(n.startswith("edited title") for _, n in notes(project_id))


def test_an_uploaded_recording_is_a_card_with_the_same_slots_and_lock(client) -> None:
    refused = client.post("/planner/upload", data={"title": "Sir on RAG"},
                          files={"video": ("rag.mp4", MP4, "video/mp4")}, follow_redirects=False)
    assert "tick the approval box" in unquote(refused.headers["location"])
    bad = client.post("/planner/upload", data={"title": "x", "approve": "yes"},
                      files={"video": ("x.mp4", b"not a video", "video/mp4")},
                      follow_redirects=False)
    assert "not an MP4" in unquote(bad.headers["location"])
    response = client.post("/planner/upload", data={"title": "Sir on RAG", "approve": "yes"},
                           files={"video": ("rag.mp4", MP4, "video/mp4")}, follow_redirects=False)
    project_id = response.headers["location"].rsplit("=", 1)[1]
    run = status(client, project_id)
    assert run["status"] == "export_ready"
    approval = run["approvals"][0]
    assert approval["stage"] == "qa_review" and approval["decision"] == "approve"
    assert approval["ai_disclosure"] == {"synthetic": False,
                                         "reason": "human content: uploaded recording"}
    with db.session() as s:
        assert s.scalars(select(AssetLicense).where(AssetLicense.project_id == project_id)).one()
    assert "Sir on RAG" in card(client, project_id) and ">Ready<" in card(client, project_id)
    slot(client, project_id, 15)
    assert scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=16)) == [project_id]
    run = status(client, project_id)
    assert run["status"] == "done"
    receipt = next(a for a in run["artifacts"] if a["type"] == "publish_receipt.json")
    assert Path(receipt["storage_path"]).name == "publish_receipt.json"


def test_cards_show_real_length_and_cost_and_planned_rows_have_a_page(client,
                                                                     monkeypatch) -> None:
    import json

    import app.nodes as nodes
    from app.nodes import stubs

    def measured(ctx):  # type: ignore[no-untyped-def]
        return stubs.rendering(ctx) | {"qa_report.json": json.dumps({"duration_s": 37.0})}

    monkeypatch.setitem(nodes.FUNCS, "rendering", measured)
    topic_id = plan(client, None)
    assert "No time yet" in client.get(f"/planner/{topic_id}").text
    project_id = ready(client)
    html = card(client, project_id)
    assert "37 s" in html and "₹0.00" in html  # its real length and cost, not "up to"
    client.post(f"/planner/{topic_id}/run")
    assert client.get(f"/planner/{topic_id}", follow_redirects=False).status_code == 303


class WorkerKilled(BaseException):
    pass


def test_firing_is_idempotent_even_when_a_worker_dies_mid_publish(client, monkeypatch) -> None:
    import app.nodes as nodes

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


def test_published_only_after_confirmation(client, monkeypatch) -> None:
    import app.nodes as nodes

    youtube = Publishing(platform="youtube", provider_video_id="abc", privacy="private",
                         confirmed_at=None, created_at=datetime.now(UTC))
    assert planner.confirmation(None, True) is None
    assert planner.confirmation(youtube, True) is None  # uploaded is not published
    youtube.confirmed_at, youtube.privacy = datetime.now(UTC), "public"
    youtube.watch_url = "https://youtu.be/abc"
    live = planner.confirmation(youtube, False)
    assert live is not None and live["label"] == "Published" and live["watch"]
    real, kills = nodes.FUNCS["mock_published"], iter([True])

    def dies_before_the_receipt(ctx):  # type: ignore[no-untyped-def]
        if next(kills, False):
            raise WorkerKilled  # the publish step is under way, nothing confirmed yet
        return real(ctx)

    monkeypatch.setitem(nodes.FUNCS, "mock_published", dies_before_the_receipt)
    project_id = ready(client)
    slot(client, project_id, 10)
    scheduler.publish_due(datetime.now(UTC) + timedelta(minutes=11))
    html = card(client, project_id)
    assert "Publishing…" in html and "Published" not in html
    assert offered(html) == {"Preview"}  # no buttons that change anything
    reaper.reap(datetime.now(UTC) + timedelta(hours=1))
    html = card(client, project_id)
    assert ">Published (mock)<" in html and ">receipt</a>" in html and "IST" in html
    from sqlalchemy import update

    from app.core.models import Artifact
    with db.session() as s, s.begin():  # no receipt on record: not confirmed, not Published
        s.execute(update(Artifact).where(
            Artifact.project_id == project_id,
            Artifact.type == "publish_receipt.json").values(stale=True))
    html = card(client, project_id)
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
    html = card(client, project_id)
    assert "pill bad" in html and ">Failed<" in html and chips(html) == 1
    assert "line 3 has no approved claim" in html and offered(html) == {"Retry"}
    assert project_id in client.get("/library?show=failed").text
    response = client.post(f"/ui/projects/{project_id}/retry", data={"back": "/library"},
                           follow_redirects=False)
    assert response.headers["location"] == "/library"
    assert "Needs your review (script)" in card(client, project_id)
