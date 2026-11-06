"""Real YouTube publishing behind `publish.mode: youtube` (D-67, D-69), against a faked Google API
(respx): never calls Google. The OAuth refresh token, never an API key; only the pinned channel;
uploads private with publishAt; synthetic-media flag + disclosure; one upload per video even
across a crash; Published only after a read-back."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from conftest import DISCLOSURE, approve, create, status
from sqlalchemy import select

from app.adapters import youtube
from app.core import config, db
from app.core.models import Publishing
from app.jobs import reaper, scheduler
from app.ui import planner

API = youtube.API_URL
CHANNEL = {"id": "UCziro", "snippet": {"title": "Ziro Digital", "customUrl": "@ziro.digital"},
           "contentDetails": {"relatedPlaylists": {"uploads": "UUziro"}}}


@pytest.fixture
def on_youtube(client, monkeypatch):  # type: ignore[no-untyped-def]
    cfg = config.load()
    cfg["publish"] = {"mode": "youtube"}
    cfg["youtube"] = {"channel_handle": "@Ziro.Digital", "channel_id": "UCziro"}
    for name in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.setenv(name, f"test-{name.lower()}")
    with respx.mock(assert_all_called=False) as google:
        google.post(youtube.TOKEN_URL).respond(json={"access_token": "test-access"})
        google.get(f"{API}/channels").respond(json={"items": [CHANNEL]})
        google.post(youtube.UPLOAD_URL).respond(headers={"Location": "https://upload.test/s1"})
        google.put("https://upload.test/s1").respond(json={"id": "vid1"})
        google.get(f"{API}/playlistItems").respond(json={"items": []})
        google.put(f"{API}/videos").respond(json={})
        yield google


def ready(client) -> str:  # type: ignore[no-untyped-def]
    project_id = create(client)
    approve(client, project_id)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    return project_id


def read_back(google, privacy: str, upload: str = "processed") -> None:  # type: ignore[no-untyped-def]
    google.get(f"{API}/videos").respond(json={"items": [{"id": "vid1", "snippet": {"tags": []},
                                                         "status": {"privacyStatus": privacy,
                                                                    "uploadStatus": upload}}]})


def uploads(google) -> list[httpx.Request]:  # type: ignore[no-untyped-def]
    return [c.request for c in google.calls if c.request.url.host == "upload.test"]


def card(client, project_id: str) -> str:  # type: ignore[no-untyped-def]
    page = client.get("/library").text
    return next(c for c in page.split("<article")[1:] if project_id in c).split("</article>")[0]


def test_a_scheduled_video_uploads_private_with_publish_at_and_is_published_after_read_back(
        client, on_youtube) -> None:
    project_id = ready(client)
    when = datetime.now(UTC) + timedelta(days=2)
    scheduler.schedule(project_id, when, "Dolender")
    assert scheduler.publish_due() == [project_id]  # uploads now, YouTube releases at the slot
    start = next(c.request for c in on_youtube.calls if c.request.url.host == "www.googleapis.com"
                 and c.request.method == "POST")
    body: dict[str, Any] = json.loads(start.content)
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == when.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert body["status"]["containsSyntheticMedia"] is True
    assert "AI disclosure:" in body["snippet"]["description"]
    assert youtube.tag(project_id) in body["snippet"]["tags"]
    assert all("key=" not in str(c.request.url) for c in on_youtube.calls)  # never an API key
    assert start.headers["Authorization"] == "Bearer test-access"
    html = card(client, project_id)
    assert "Scheduled ·" in html and "Published" not in html  # uploaded, not released

    read_back(on_youtube, "private")
    assert scheduler.confirm_due() == []  # before the slot: not confirmed
    assert scheduler.confirm_due(when + timedelta(minutes=1)) == [project_id]
    html = card(client, project_id)
    assert "Published · private" in html and "https://youtu.be/vid1" in html and "vid1" in html


def test_publish_now_uploads_then_releases_and_confirms_public(client, on_youtube) -> None:
    project_id = ready(client)
    read_back(on_youtube, "public")
    scheduler.publish_now(project_id, "Dolender")
    released = [json.loads(c.request.content) for c in on_youtube.calls
                if c.request.method == "PUT" and c.request.url.path.endswith("/videos")]
    assert released[-1]["status"]["privacyStatus"] == "public"
    assert "publishAt" not in json.loads(next(
        c.request.content for c in on_youtube.calls if c.request.method == "POST"
        and c.request.url.host == "www.googleapis.com"))["status"]
    assert scheduler.confirm_due() == [project_id]
    assert ">Published<" in card(client, project_id)


def test_reschedule_and_unschedule_change_the_uploaded_video(client, on_youtube) -> None:
    project_id = ready(client)
    scheduler.schedule(project_id, datetime.now(UTC) + timedelta(days=2), "Dolender")
    scheduler.publish_due()
    read_back(on_youtube, "private", "uploaded")
    later = datetime.now(UTC) + timedelta(days=5)
    scheduler.schedule(project_id, later, "Dolender")
    sent = json.loads(on_youtube.calls[-1].request.content)
    assert sent == {"id": "vid1", "status": {"privacyStatus": "private",
                                             "selfDeclaredMadeForKids": False,
                                             "publishAt": later.strftime("%Y-%m-%dT%H:%M:%SZ")}}
    scheduler.schedule(project_id, None, "Dolender")
    assert "publishAt" not in json.loads(on_youtube.calls[-1].request.content)["status"]
    assert "Ready · on YouTube, private" in card(client, project_id)
    assert len(uploads(on_youtube)) == 1  # changed in place, never uploaded again


def test_missing_oauth_token_fails_with_the_reason_and_uploads_nothing(client, on_youtube,
                                                                      monkeypatch) -> None:
    monkeypatch.delenv("YT_REFRESH_TOKEN")
    project_id = ready(client)
    scheduler.publish_now(project_id, "Dolender")
    run = status(client, project_id)
    assert run["status"] == "failed"
    assert "missing OAuth token: YT_REFRESH_TOKEN" in run["jobs"][-1]["error_message"]
    assert uploads(on_youtube) == []
    html = card(client, project_id)
    assert ">Failed<" in html and "missing OAuth token" in html and "/retry" in html


def test_a_token_for_another_channel_is_refused_before_any_upload(client, on_youtube) -> None:
    other = CHANNEL | {"id": "UCother", "snippet": {"title": "Test", "customUrl": "@sometest"}}
    on_youtube.get(f"{API}/channels").respond(json={"items": [other]})
    project_id = ready(client)
    scheduler.publish_now(project_id, "Dolender")
    assert "is not @Ziro.Digital" in status(client, project_id)["jobs"][-1]["error_message"]
    assert uploads(on_youtube) == []


def test_a_crash_after_youtube_got_the_file_never_uploads_it_twice(client, on_youtube,
                                                                   monkeypatch) -> None:
    real, crashes = youtube.YouTubePublisher._upload, iter([True])

    class WorkerKilled(BaseException):
        pass

    def upload_then_die(self, *args):  # type: ignore[no-untyped-def]
        video_id = real(self, *args)  # YouTube has the file...
        if next(crashes, False):
            raise WorkerKilled  # ...and the worker dies before recording it
        return video_id

    monkeypatch.setattr(youtube.YouTubePublisher, "_upload", upload_then_die)
    project_id = ready(client)
    scheduler.schedule(project_id, datetime.now(UTC) + timedelta(days=1), "Dolender")
    scheduler.publish_due()
    assert len(uploads(on_youtube)) == 1  # the file went to YouTube once
    on_youtube.get(f"{API}/playlistItems").respond(
        json={"items": [{"contentDetails": {"videoId": "vid1"}}]})
    on_youtube.get(f"{API}/videos").respond(json={"items": [
        {"id": "vid1", "snippet": {"tags": [youtube.tag(project_id)]}}]})
    assert reaper.reap(datetime.now(UTC) + timedelta(hours=1)) == [project_id]  # a restart
    assert len(uploads(on_youtube)) == 1  # found by its tag, not uploaded again
    with db.session() as s:
        row = s.scalars(select(Publishing).where(Publishing.project_id == project_id)).one()
    assert (row.provider_video_id, row.status) == ("vid1", "uploaded")
    assert status(client, project_id)["status"] == "done"


def test_publishing_without_the_final_approval_is_unreachable_on_youtube(client,
                                                                        on_youtube) -> None:
    project_id = create(client)
    approve(client, project_id)  # final review still open
    with pytest.raises(ValueError, match="only an approved video"):
        scheduler.publish_now(project_id, "Dolender")
    assert uploads(on_youtube) == [] and planner.one(project_id)["key"] == "review_video"
