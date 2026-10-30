"""Audit tables (ARCHITECTURE §6 + D-15): the audit log, not LangGraph checkpoints (D-12)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict[str, Any]: JSON}


def _project_fk() -> Mapped[str]:
    return mapped_column(ForeignKey("projects.id"), index=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str]
    topic: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text)
    language: Mapped[str]
    format: Mapped[str]
    target_seconds: Mapped[int]
    cta: Mapped[str] = mapped_column(Text)
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = _project_fk()
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    accessed_at: Mapped[datetime]
    published_at: Mapped[datetime | None]
    claim: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = _project_fk()
    stage: Mapped[str]
    type: Mapped[str]
    version: Mapped[int]
    storage_path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str]
    model_or_tool: Mapped[str]
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(unique=True)
    project_id: Mapped[str] = _project_fk()
    stage: Mapped[str]
    approver: Mapped[str]
    decision: Mapped[str]
    target_stage: Mapped[str | None]
    notes: Mapped[str] = mapped_column(Text, default="")
    ai_disclosure: Mapped[dict[str, Any] | None]
    claim_edits: Mapped[dict[str, Any] | None]
    artifact_version: Mapped[int]
    opened_at: Mapped[datetime]
    timestamp: Mapped[datetime] = mapped_column(default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = _project_fk()
    stage: Mapped[str]
    status: Mapped[str]
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=now)
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)


class Publishing(Base):
    __tablename__ = "publishing"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = _project_fk()
    idempotency_key: Mapped[str] = mapped_column(unique=True)
    platform: Mapped[str]
    channel_id: Mapped[str | None]
    privacy: Mapped[str]
    scheduled_at: Mapped[datetime | None]
    provider_video_id: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Cost(Base):
    __tablename__ = "costs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = _project_fk()
    stage: Mapped[str]
    provider: Mapped[str]
    units: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    observed_or_estimate: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = _project_fk()
    from_state: Mapped[str | None]
    to_state: Mapped[str]
    actor: Mapped[str]
    at: Mapped[datetime] = mapped_column(default=now)


class AssetLicense(Base):
    __tablename__ = "asset_licenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset: Mapped[str] = mapped_column(Text)
    type: Mapped[str]
    source: Mapped[str] = mapped_column(Text)
    license: Mapped[str]
    proof_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now)
