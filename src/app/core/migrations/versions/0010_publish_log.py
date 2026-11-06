"""Publish log and audit notes (D-69): a publish is confirmed only by a read-back (when, and the
watch link), and actions that are not state changes (schedule, publish now, metadata edits) go
into the audit trail with who, when and what.

Revision ID: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.add_column("publishing", sa.Column("confirmed_at", sa.DateTime(timezone=True)))
    op.add_column("publishing", sa.Column("watch_url", sa.Text))
    op.add_column("events", sa.Column("note", sa.Text))


def downgrade() -> None:
    op.drop_column("events", "note")
    op.drop_column("publishing", "watch_url")
    op.drop_column("publishing", "confirmed_at")
