"""Archived videos (D-73): hidden from the Library's other filters, the Planner and the "Needs
you" badge; kept, never deleted, and listed under the Library's Archived filter.

Revision ID: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.add_column("projects", sa.Column("archived", sa.Boolean, nullable=False,
                                        server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("projects", "archived")
