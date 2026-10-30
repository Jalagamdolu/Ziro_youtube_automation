"""Audit tables: ARCHITECTURE §6 + D-15.

Revision ID: 0001
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None

TS = sa.DateTime(timezone=True)


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.Integer, primary_key=True)


def _project() -> sa.Column[str]:
    return sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id"), nullable=False,
                     index=True)


def _created() -> sa.Column[datetime]:
    return sa.Column("created_at", TS, nullable=False)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner", sa.String, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("audience", sa.Text, nullable=False),
        sa.Column("language", sa.String, nullable=False),
        sa.Column("format", sa.String, nullable=False),
        sa.Column("target_seconds", sa.Integer, nullable=False),
        sa.Column("cta", sa.Text, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        _created(),
    )
    op.create_table(
        "sources",
        _id(), _project(),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("accessed_at", TS, nullable=False),
        sa.Column("published_at", TS),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("verification_status", sa.String, nullable=False),
        _created(),
    )
    op.create_table(
        "artifacts",
        _id(), _project(),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("checksum", sa.String, nullable=False),
        sa.Column("model_or_tool", sa.String, nullable=False),
        sa.Column("stale", sa.Boolean, nullable=False),
        _created(),
    )
    op.create_table(
        "approvals",
        _id(),
        sa.Column("decision_id", sa.String, nullable=False, unique=True),
        _project(),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("approver", sa.String, nullable=False),
        sa.Column("decision", sa.String, nullable=False),
        sa.Column("target_stage", sa.String),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("ai_disclosure", sa.JSON),
        sa.Column("artifact_version", sa.Integer, nullable=False),
        sa.Column("opened_at", TS, nullable=False),
        sa.Column("timestamp", TS, nullable=False),
    )
    op.create_table(
        "jobs",
        _id(), _project(),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("retry_count", sa.Integer, nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("finished_at", TS),
        sa.Column("error_code", sa.String),
        sa.Column("error_message", sa.Text),
        sa.Column("cost_estimate", sa.Float, nullable=False),
    )
    op.create_table(
        "publishing",
        _id(), _project(),
        sa.Column("idempotency_key", sa.String, nullable=False, unique=True),
        sa.Column("platform", sa.String, nullable=False),
        sa.Column("channel_id", sa.String),
        sa.Column("privacy", sa.String, nullable=False),
        sa.Column("scheduled_at", TS),
        sa.Column("provider_video_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        _created(),
    )
    op.create_table(
        "costs",
        _id(), _project(),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("units", sa.Float, nullable=False),
        sa.Column("unit_price", sa.Float, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("observed_or_estimate", sa.String, nullable=False),
        _created(),
    )
    op.create_table(
        "events",
        _id(), _project(),
        sa.Column("from_state", sa.String),
        sa.Column("to_state", sa.String, nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("at", TS, nullable=False),
    )
    op.create_table(
        "asset_licenses",
        _id(),
        sa.Column("asset", sa.Text, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("license", sa.String, nullable=False),
        sa.Column("proof_url", sa.Text),
        _created(),
    )


def downgrade() -> None:
    for table in ("asset_licenses", "events", "costs", "publishing", "jobs", "approvals",
                  "artifacts", "sources", "projects"):
        op.drop_table(table)
