"""Publisher adapter (D-06, D-69). Publishing needs an ApprovedRun, which only approved_run() can
build, and that only succeeds when the latest qa_review decision in `approvals` is "approve".

Providers by `publish.mode`: mock (default) records a private fake upload; youtube uploads to the
one pinned channel (D-67, app.adapters.youtube). Both are idempotent on the video: a repeat
returns the first row, so the same video is never published twice.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import config
from app.core.errors import FatalError
from app.core.models import Approval, Publishing

_KEY = object()


@dataclass(frozen=True)
class ApprovedRun:
    project_id: str
    approval_id: int
    disclosure: dict[str, Any]
    _key: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._key is not _KEY:
            raise TypeError("ApprovedRun can only be created by approved_run()")


def approved_run(s: Session, project_id: str) -> ApprovedRun:
    latest = s.scalars(
        select(Approval)
        .where(Approval.project_id == project_id, Approval.stage == "qa_review")
        .order_by(Approval.timestamp.desc())
        .limit(1)
    ).first()
    if latest is None or latest.decision != "approve":
        raise FatalError("publish refused: qa_review is not approved")
    return ApprovedRun(project_id, latest.id, latest.ai_disclosure or {}, _KEY)


def request(run: ApprovedRun, title: str, description: str, tags: list[str], language: str,
            generated: bool) -> dict[str, Any]:
    """The videos.insert body. Every upload carries the AI disclosure in its description and
    containsSyntheticMedia; a pipeline video always has AI narration, so it is always true."""
    synthetic = generated or bool(run.disclosure.get("synthetic"))
    reason = run.disclosure.get("reason", "")
    note = (f"AI disclosure: this video contains AI-generated or altered content ({reason})."
            if synthetic else f"Disclosure: {reason}.")
    return {"snippet": {"title": title, "description": f"{description}\n\n{note}".strip(),
                        "tags": tags, "categoryId": "27", "defaultLanguage": language},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": synthetic}}


class Publisher(Protocol):
    platform: str

    def publish(self, s: Session, run: ApprovedRun, body: dict[str, Any], video_key: str,
                when: datetime | None) -> Publishing: ...


class MockPublisher:
    """Records a fake private upload at the slot (the scheduler fires mock at the minute)."""

    platform = "youtube-mock"

    def publish(self, s: Session, run: ApprovedRun, body: dict[str, Any], video_key: str = "",
                when: datetime | None = None) -> Publishing:
        existing = s.scalars(
            select(Publishing).where(Publishing.idempotency_key == run.project_id)
        ).first()
        if existing is not None:
            return existing
        row = Publishing(
            project_id=run.project_id,
            idempotency_key=run.project_id,
            platform=self.platform,
            channel_id=None,
            privacy=body["status"]["privacyStatus"],
            scheduled_at=None,
            provider_video_id="mock-" + hashlib.sha256(run.project_id.encode()).hexdigest()[:11],
            status="mock_published",
        )
        s.add(row)
        s.flush()
        return row


def mode() -> str:
    return str(config.load().get("publish", {}).get("mode", "mock"))


def get() -> Publisher:
    if mode() == "youtube":
        from app.adapters.youtube import YouTubePublisher

        return YouTubePublisher()
    return MockPublisher()
