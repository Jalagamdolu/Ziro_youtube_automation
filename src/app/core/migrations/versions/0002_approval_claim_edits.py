"""Per-claim research_review edits (D-20).

Revision ID: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.add_column("approvals", sa.Column("claim_edits", sa.JSON))


def downgrade() -> None:
    op.drop_column("approvals", "claim_edits")
