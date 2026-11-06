"""Topic scheduler (D-47): APScheduler in the API process checks the planner every minute.

- A planned topic's run starts `planner.start_hours_before` (3 h) before its publish_at, so both
  reviews fit; "Run now" starts it at once through the same path.
- A run from a topic publishes (mock) at publish_at, never earlier: after the final approval it
  waits at export_ready, and this scheduler resumes it when the time comes.
- Nothing publishes without both reviews: the Publisher refuses a run without an approved
  qa_review (D-06). A finished video waits as Ready until it has a time slot; only a video
  approved before its slot publishes at it. Missed the slot in review: it waits, shown as
  Missed, until it gets a new time (D-64).
- Uploaded recordings (D-64) get the same slots and lock: a row with a manual final approval
  ("human content"), published by publish_upload() instead of a pipeline run.
- Publish now (D-69) is a slot at this minute. In youtube mode a slotted video uploads at once,
  private, with status.publishAt = its slot, so YouTube releases it even if this machine is off;
  a later reschedule / unschedule / publish-early changes that uploaded video. Published is set
  only by confirm_due's read-back, never on send (D-66).
- Every action (schedule, unschedule, publish now) is an audit row: who, when, what.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.adapters import publisher, storage
from app.adapters.publisher import approved_run
from app.core import audit, config, db
from app.core.log import log
from app.core.models import Approval, Artifact, AssetLicense, Event, Project, Publishing, Topic
from app.jobs.queue import enqueue_once

WAITING = "export_ready"  # a Ready video: approved, waiting for its slot (D-64)
FIRING = "publishing"  # a row whose slot the scheduler has fired


def firing(project_id: str) -> bool:
    """Whether the scheduler has fired this video's slot; the graph publishes only then."""
    with db.session() as s:
        return s.scalar(select(Topic.status).where(Topic.project_id == project_id)) == FIRING


def start_topic(topic_id: int, actor: str) -> str | None:
    """Create the topic's run once (a planned topic only); returns the project id."""
    from app.api import actions  # actions imports the graph stages; keep this module light

    with db.session() as s, s.begin():
        claimed = s.execute(update(Topic).where(Topic.id == topic_id, Topic.status == "planned")
                            .values(status="starting")).rowcount  # type: ignore[attr-defined]
        topic = s.get_one(Topic, topic_id)
        request = actions.CreateRequest(
            prompt=topic.topic, format="long" if topic.format == "long" else "short",
            target_seconds=topic.target_seconds, keywords=topic.keywords,
            guidelines=topic.guidelines, owner=actor)
    if not claimed:
        return None
    try:
        project_id = actions.create_project(request)
    except Exception:
        with db.session() as s, s.begin():
            s.execute(update(Topic).where(Topic.id == topic_id).values(status="planned"))
        raise
    with db.session() as s, s.begin():
        s.execute(update(Topic).where(Topic.id == topic_id)
                  .values(status="started", project_id=project_id))
    log.info("topic run started", topic_id=topic_id, project_id=project_id, actor=actor)
    return project_id


def start_due(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    lead = timedelta(hours=config.load()["planner"]["start_hours_before"])
    with db.session() as s:
        due = s.scalars(select(Topic.id).where(Topic.status == "planned",
                                               Topic.publish_at.is_not(None),
                                               Topic.publish_at <= now + lead)).all()
    return [p for topic_id in due if (p := start_topic(topic_id, "scheduler"))]


def publish_at(project_id: str) -> datetime | None:
    with db.session() as s:
        return s.scalar(select(Topic.publish_at).where(Topic.project_id == project_id))


def final_approved_at(s: Any, project_id: str) -> datetime | None:
    """When the final video was approved (the latest qa_review decision, if it is an approve)."""
    latest = s.scalars(select(Approval).where(Approval.project_id == project_id,
                                              Approval.stage == "qa_review")
                       .order_by(Approval.timestamp.desc()).limit(1)).first()
    return latest.timestamp if latest and latest.decision == "approve" else None


def publish_due(now: datetime | None = None) -> list[str]:
    """Publish Ready videos whose slot has come, if they were approved before it (D-64)."""
    now = now or datetime.now(UTC)
    # youtube uploads a slotted video at once with publishAt; mock fires at the minute
    horizon = datetime.max.replace(tzinfo=UTC) if publisher.mode() == "youtube" else now
    with db.session() as s:
        rows = s.execute(select(Project.id, Topic.kind, Topic.publish_at)
                         .join(Topic, Topic.project_id == Project.id)
                         .where(Project.status == WAITING, Topic.publish_at.is_not(None),
                                Topic.publish_at <= horizon)).all()
        due = [(p, kind) for p, kind, when in rows
               if when is not None and (approved := final_approved_at(s, p)) is not None
               and approved <= when]
    published = []
    for project_id, kind in due:
        with db.session() as s, s.begin():  # the graph publishes only a row marked firing
            s.execute(update(Topic).where(Topic.project_id == project_id)
                      .values(status=FIRING))
        if kind == "upload":
            publish_upload(project_id)
            published.append(project_id)
        elif enqueue_once(f"{project_id}:publish:{_slot(project_id)}", project_id, {"due": True}):
            published.append(project_id)
    for project_id in published:
        log.info("publish time reached", project_id=project_id)
    return published


def _slot(project_id: str) -> str:
    """The job id part for this slot, so a rescheduled video gets a fresh publish job."""
    when = publish_at(project_id)
    return str(int(when.timestamp())) if when else "none"


def uploaded(s: Any, project_id: str) -> Publishing | None:
    """A video already on YouTube but not confirmed released (youtube mode, D-69)."""
    row = s.scalars(select(Publishing).where(Publishing.project_id == project_id)).first()
    if row and row.platform == "youtube" and row.provider_video_id and row.confirmed_at is None:
        return row  # type: ignore[no-any-return]
    return None


def schedule(project_id: str, when: datetime | None, actor: str) -> None:
    """Set, change or clear a Ready video's publish time (D-64). Refused unless the final video
    is approved and not yet published: no final approval, no scheduling."""
    with db.session() as s:
        on_youtube = uploaded(s, project_id)
    if on_youtube is not None:
        return _release(project_id, on_youtube.provider_video_id, when, False, actor)
    with db.session() as s, s.begin():
        project = s.get_one(Project, project_id)
        if project.status != WAITING or final_approved_at(s, project_id) is None:
            raise ValueError("only an approved video that is not yet published can be scheduled")
        if firing(project_id):
            raise ValueError("it is publishing now")
        if when is not None and when <= datetime.now(UTC):
            raise ValueError("pick a time in the future")
        topic = s.scalars(select(Topic).where(Topic.project_id == project_id)).first()
        if topic is None:
            s.add(Topic(topic=project.topic, keywords=[], guidelines="", format=project.format,
                        target_seconds=project.target_seconds, publish_at=when, status="started",
                        project_id=project_id, created_by=actor))
        else:
            topic.publish_at = when
        audit.action(s, project_id, actor, f"scheduled for {when.isoformat()}" if when
                     else "unscheduled")
    log.info("publish time set", project_id=project_id, publish_at=str(when), actor=actor)


def publish_now(project_id: str, actor: str) -> None:
    """Publish now (D-69): a slot at this minute, fired at once, under the same lock. On a video
    already uploaded ahead to YouTube it releases it early instead."""
    with db.session() as s:
        on_youtube = uploaded(s, project_id)
    if on_youtube is not None:
        _release(project_id, on_youtube.provider_video_id, None, True, actor)
        confirm_due()
        return
    now = datetime.now(UTC)
    with db.session() as s, s.begin():
        project = s.get_one(Project, project_id)
        if project.status != WAITING or final_approved_at(s, project_id) is None:
            raise ValueError("only an approved video that is not yet published can be published")
        if firing(project_id):
            raise ValueError("it is publishing now")
        topic = s.scalars(select(Topic).where(Topic.project_id == project_id)).first()
        if topic is None:
            s.add(Topic(topic=project.topic, keywords=[], guidelines="", format=project.format,
                        target_seconds=project.target_seconds, publish_at=now, status="started",
                        project_id=project_id, created_by=actor))
        else:
            topic.publish_at = now
        audit.action(s, project_id, actor, "publish now")
    publish_due(now)


def _release(project_id: str, video_id: str, when: datetime | None, public: bool,
             actor: str) -> None:
    """Reschedule, unschedule or publish early a video already on YouTube."""
    from app.adapters import youtube

    if when is not None and when <= datetime.now(UTC):
        raise ValueError("pick a time in the future")
    privacy = youtube.set_release(video_id, when, public)
    with db.session() as s, s.begin():
        row = s.scalars(select(Publishing).where(Publishing.project_id == project_id)).one()
        row.scheduled_at, row.privacy = (None if public else when), privacy
        s.execute(update(Topic).where(Topic.project_id == project_id)
                  .values(publish_at=datetime.now(UTC) if public else when))
        audit.action(s, project_id, actor, "published early on YouTube" if public else
                     f"rescheduled on YouTube for {when.isoformat()}" if when
                     else "unscheduled on YouTube (stays private)")


def confirm_due(now: datetime | None = None) -> list[str]:
    """Confirm YouTube uploads that should be live by reading them back (D-66): only then do
    they show as Published, with the watch link and the time."""
    from app.adapters import youtube

    now = now or datetime.now(UTC)
    with db.session() as s:
        due = [r.project_id for r in s.scalars(select(Publishing).where(
            Publishing.platform == "youtube", Publishing.confirmed_at.is_(None),
            Publishing.provider_video_id != "")) if r.privacy == "public" or (
            r.scheduled_at is not None and r.scheduled_at <= now)]
    confirmed = []
    for project_id in due:
        with db.session() as s, s.begin():
            row = s.scalars(select(Publishing).where(Publishing.project_id == project_id)).one()
            if youtube.confirm(row, now):
                audit.action(s, project_id, "scheduler",
                             f"confirmed on YouTube ({row.privacy}): {row.watch_url}")
                confirmed.append(project_id)
    return confirmed


MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def upload(title: str, video: bytes, filename: str, approver: str) -> str:
    """An external MP4 (e.g. sir's recording) as a planner row (D-64): stored, licensed as
    Ziro's own, approved by hand with the disclosure "human content", and Ready."""
    if b"ftyp" not in video[4:12]:
        raise ValueError("that file is not an MP4 video")
    if len(video) > MAX_UPLOAD_BYTES:
        raise ValueError("the video is larger than 500 MB")
    now = datetime.now(UTC)
    project_id = hashlib.sha256(f"{title}{now.isoformat()}".encode()).hexdigest()[:32]
    key = storage.get().write(f"{project_id}/upload/v1/video.mp4", video)
    with db.session() as s, s.begin():
        s.add(Project(id=project_id, owner=approver, topic=title, audience="", language="en",
                      format="short", target_seconds=60, cta="", status=WAITING))
        s.flush()
        s.add(Event(project_id=project_id, from_state=None, to_state=WAITING, actor=approver))
        s.add(Artifact(project_id=project_id, stage="upload", type="video.mp4", version=1,
                       storage_path=key, checksum=hashlib.sha256(video).hexdigest(),
                       model_or_tool="upload"))
        s.add(Approval(decision_id=f"{project_id}:qa_review:1", project_id=project_id,
                       stage="qa_review", approver=approver, decision="approve",
                       notes="Uploaded recording, approved by hand at upload.",
                       ai_disclosure={"synthetic": False,
                                      "reason": "human content: uploaded recording"},
                       artifact_version=1, opened_at=now, timestamp=now))
        s.add(AssetLicense(asset=f"uploaded recording {filename}", type="upload",
                           source=f"uploaded by {approver}", project_id=project_id,
                           license="Ziro's own recording, uploaded by its reviewer (D-64)",
                           proof_url=None))
        s.add(Topic(topic=title, keywords=[], guidelines="", format="short",
                    target_seconds=None, publish_at=None, status="started",
                    project_id=project_id, created_by=approver, kind="upload"))
    log.info("video uploaded", project_id=project_id, actor=approver, size=len(video))
    return project_id


def publish_upload(project_id: str) -> None:
    """Publish an uploaded recording through the same Publisher lock (D-06), same provider."""
    from app.core import metadata

    with db.session() as s, s.begin():
        project = s.get_one(Project, project_id)
        run = approved_run(s, project_id)
        meta = metadata.edited(s, project_id) or {"title": project.topic, "description": "",
                                                  "tags": []}
        request = publisher.request(run, meta["title"], meta["description"], meta["tags"],
                                    project.language, generated=False)
        video = s.scalars(select(Artifact.storage_path).where(
            Artifact.project_id == project_id, Artifact.type == "video.mp4")).one()
        row = publisher.get().publish(s, run, request, video, publish_at(project_id))
        receipt = {"request": request, "platform": row.platform,
                   "video_id": row.provider_video_id, "idempotency_key": row.idempotency_key,
                   "mocked": row.platform != "youtube", "publish_at": str(row.scheduled_at)}
        data = json.dumps(receipt, indent=2).encode()
        key = storage.get().write(f"{project_id}/mock_published/v1/publish_receipt.json", data)
        s.add(Artifact(project_id=project_id, stage="mock_published",
                       type="publish_receipt.json", version=1, storage_path=key,
                       checksum=hashlib.sha256(data).hexdigest(), model_or_tool="mock"))
        audit.transition(s, project_id, "done", actor="scheduler")


def waiting_for_publish(project: Project, now: datetime) -> bool:
    """For the reaper: a Ready video parked until its slot is not stalled (D-64)."""
    return project.status == WAITING


def tick() -> dict[str, Any]:
    started, published = start_due(), publish_due()
    confirmed = confirm_due() if publisher.mode() == "youtube" else []
    return {"started": started, "published": published, "confirmed": confirmed}


def start() -> Any:
    """The APScheduler job, started from the API's lifespan."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_safe_tick, "interval", seconds=config.load()["planner"]["check_seconds"],
                      next_run_time=datetime.now(UTC))
    scheduler.start()
    return scheduler


def _safe_tick() -> None:
    try:
        tick()
    except Exception as error:
        log.error("scheduler tick failed", error=str(error))
