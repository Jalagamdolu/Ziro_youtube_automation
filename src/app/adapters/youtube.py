"""YouTube Data API publisher (D-67, D-69), used only when `publish.mode: youtube`.

- Auth: the OAuth refresh token from .env (YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN),
  never an API key. Missing → FatalError (the §08 "missing OAuth token" failure).
- Target: only the channel pinned in config; checked before every call that changes a video.
- Upload: always private. A slot goes in status.publishAt, so YouTube releases it at that minute
  even if this machine is off; "Publish now" uploads private, then sets it public.
- Never twice: a `publishing` row claims the video (committed) before the upload, and every
  upload carries a tag made from the idempotency key. An attempt that died mid-upload is found by
  that tag on retry instead of uploading again.
- Errors: timeouts, 429 and 5xx are retryable; any other refusal is fatal, with YouTube's reason.
"""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import storage
from app.adapters.publisher import ApprovedRun
from app.api import youtube_auth
from app.core import config, db
from app.core.errors import FatalError, RetryableError
from app.core.models import Publishing

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://www.googleapis.com/youtube/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SOON = timedelta(minutes=5)  # publishAt must be in the future; a slot closer than this is "now"
WATCH = "https://youtu.be/{}"


def _call(method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        reply = httpx.request(method, url, timeout=kwargs.pop("timeout", 60), **kwargs)
    except httpx.TransportError as error:
        raise RetryableError(f"YouTube unreachable: {type(error).__name__}") from error
    if reply.status_code == 429 or reply.status_code >= 500:
        raise RetryableError(f"YouTube answered {reply.status_code}")
    if reply.status_code >= 400:
        raise FatalError(f"YouTube refused ({reply.status_code}): {_reason(reply)}")
    return reply


def _reason(reply: httpx.Response) -> str:
    try:
        error = reply.json()["error"]
        return str(error.get("message") or error)[:200]
    except (ValueError, KeyError, TypeError):
        return reply.text[:200]


def access_token() -> str:
    names = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise FatalError(f"missing OAuth token: {', '.join(missing)} not set in .env "
                         "(run make youtube-auth)")
    reply = _call("POST", TOKEN_URL, data={
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    return str(reply.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def pinned_channel(token: str) -> str:
    """The token's channel must be the pinned one (handle and ID); returns its ID."""
    target = config.load()["youtube"]
    if not target.get("channel_id"):
        raise FatalError("publish refused: no channel pinned in config (run make youtube-auth)")
    items = _call("GET", f"{API_URL}/channels", params={"part": "snippet", "mine": "true"},
                  headers=_auth(token)).json().get("items", [])
    if len(items) != 1 or not youtube_auth.matches(items[0], target["channel_handle"],
                                                   target["channel_id"]):
        raise FatalError(f"publish refused: the token's channel is not {target['channel_handle']}"
                         f" ({target['channel_id']})")
    return str(target["channel_id"])


def tag(idempotency_key: str) -> str:
    return "ziro" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]


def find_tagged(token: str, mark: str) -> str | None:
    """A recent upload on the channel carrying this tag (an attempt that died mid-upload)."""
    channel = _call("GET", f"{API_URL}/channels", params={"part": "contentDetails", "mine": "true"},
                    headers=_auth(token)).json()["items"][0]
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    items = _call("GET", f"{API_URL}/playlistItems", headers=_auth(token), params={
        "part": "contentDetails", "playlistId": uploads, "maxResults": 50}).json().get("items", [])
    ids = [item["contentDetails"]["videoId"] for item in items]
    if not ids:
        return None
    videos = _call("GET", f"{API_URL}/videos", headers=_auth(token), params={
        "part": "snippet", "id": ",".join(ids)}).json().get("items", [])
    return next((v["id"] for v in videos if mark in v["snippet"].get("tags", [])), None)


def read_back(video_id: str, token: str | None = None) -> dict[str, Any] | None:
    """The video's status as YouTube has it now, or None if YouTube does not have it."""
    token = token or access_token()
    items = _call("GET", f"{API_URL}/videos", params={"part": "status", "id": video_id},
                  headers=_auth(token)).json().get("items", [])
    return items[0]["status"] if items else None


def set_release(video_id: str, when: datetime | None, public: bool) -> str:
    """Reschedule (when), unschedule (no when, private) or publish now (public) an uploaded
    video. The current status is read first so containsSyntheticMedia and the rest are kept."""
    token = access_token()
    pinned_channel(token)
    status = dict(read_back(video_id, token) or {})
    if not status:
        raise FatalError(f"YouTube has no video {video_id}")
    keep = ("embeddable", "license", "publicStatsViewable", "containsSyntheticMedia")
    body = {key: status[key] for key in keep if key in status}
    body |= {"privacyStatus": "public" if public else "private", "selfDeclaredMadeForKids": False}
    if when is not None and not public:
        body["publishAt"] = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _call("PUT", f"{API_URL}/videos", params={"part": "status"}, headers=_auth(token),
          json={"id": video_id, "status": body})
    return str(body["privacyStatus"])


class YouTubePublisher:
    platform = "youtube"

    def publish(self, s: Session, run: ApprovedRun, body: dict[str, Any], video_key: str,
                when: datetime | None) -> Publishing:
        key = run.project_id
        existing = s.scalars(select(Publishing).where(Publishing.idempotency_key == key)).first()
        if existing is not None and existing.provider_video_id:
            return existing  # uploaded before: never again
        token = access_token()
        channel = pinned_channel(token)
        now_ = when is None or when <= datetime.now(UTC) + SOON
        mark = tag(key)
        found = None
        if existing is None:
            with db.session() as claim, claim.begin():  # committed before YouTube sees a byte
                claim.add(Publishing(project_id=key, idempotency_key=key, platform=self.platform,
                                     channel_id=channel, privacy="private", scheduled_at=when,
                                     provider_video_id="", status="uploading"))
        else:
            found = find_tagged(token, mark)  # an earlier attempt may have reached YouTube
        video_id = found or self._upload(token, body, mark, storage.get().read(video_key),
                                         None if now_ else when)
        privacy = set_release(video_id, None, public=True) if now_ else "private"
        row = s.scalars(select(Publishing).where(Publishing.idempotency_key == key)).one()
        row.provider_video_id, row.status, row.privacy = video_id, "uploaded", privacy
        row.scheduled_at = None if now_ else when
        s.flush()
        return row

    def _upload(self, token: str, body: dict[str, Any], mark: str, data: bytes,
                when: datetime | None) -> str:
        sent = {"snippet": {**body["snippet"], "tags": [*body["snippet"].get("tags", []), mark]},
                "status": {**body["status"], "privacyStatus": "private"}}
        if when is not None:
            sent["status"]["publishAt"] = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        start = _call("POST", UPLOAD_URL, params={"uploadType": "resumable",
                                                  "part": "snippet,status"},
                      headers={**_auth(token), "X-Upload-Content-Type": "video/mp4",
                               "X-Upload-Content-Length": str(len(data))}, json=sent)
        done = _call("PUT", start.headers["Location"], timeout=600, content=data,
                     headers={**_auth(token), "Content-Type": "video/mp4"})
        return str(done.json()["id"])


def confirm(row: Publishing, now: datetime) -> bool:
    """Read-back confirmation (D-66): public, or its publishAt has passed and YouTube finished
    processing it (a new, unaudited API project keeps uploads private). Sets confirmed_at and the
    watch link; True when confirmed."""
    status = read_back(row.provider_video_id)
    if status is None:
        return False
    public = status.get("privacyStatus") == "public"
    released = row.scheduled_at is not None and now >= row.scheduled_at
    if not (public or (released and status.get("uploadStatus") == "processed")):
        return False
    row.confirmed_at, row.privacy = now, str(status.get("privacyStatus"))
    row.watch_url = WATCH.format(row.provider_video_id)
    return True
