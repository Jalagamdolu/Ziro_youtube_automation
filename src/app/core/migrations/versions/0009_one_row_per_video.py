"""One planner row per video (D-64): a row's publish time is optional (planned without a slot,
or a Ready video waiting for one), and a row is a generated video or an uploaded recording.

Revision ID: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.alter_column("topics", "publish_at", existing_type=sa.DateTime(timezone=True),
                    nullable=True)
    op.add_column("topics", sa.Column("kind", sa.String, nullable=False,
                                      server_default="generated"))


def downgrade() -> None:
    op.drop_column("topics", "kind")
    op.execute("DELETE FROM topics WHERE publish_at IS NULL")
    op.alter_column("topics", "publish_at", existing_type=sa.DateTime(timezone=True),
                    nullable=False)
