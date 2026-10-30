"""Publisher adapter (D-06). Publishing needs an ApprovedRun, which only approved_run() can build,
and that only succeeds when the latest qa_review decision in `approvals` is "approve".
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import FatalError
from app.core.models import Approval, Publishing

_KEY = object()


@dataclass(frozen=True)
class ApprovedRun:
    project_id: str
    approval_id: int
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
    return ApprovedRun(project_id, latest.id, _KEY)


class Publisher(Protocol):
    def publish(self, s: Session, run: ApprovedRun, request: dict[str, Any]) -> Publishing: ...


class MockPublisher:
    """Records a fake private upload. Idempotent on project_id: a repeat returns the first row."""

    def publish(self, s: Session, run: ApprovedRun, request: dict[str, Any]) -> Publishing:
        existing = s.scalars(
            select(Publishing).where(Publishing.idempotency_key == run.project_id)
        ).first()
        if existing is not None:
            return existing
        row = Publishing(
            project_id=run.project_id,
            idempotency_key=run.project_id,
            platform="youtube-mock",
            channel_id=None,
            privacy=request["status"]["privacyStatus"],
            scheduled_at=None,
            provider_video_id="mock-" + hashlib.sha256(run.project_id.encode()).hexdigest()[:11],
            status="mock_published",
        )
        s.add(row)
        s.flush()
        return row
