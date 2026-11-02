"""Asset licenses per run: stock footage rows carry the run and the search query.

Revision ID: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.add_column("asset_licenses", sa.Column("project_id", sa.String(32), nullable=True))
    op.add_column("asset_licenses", sa.Column("query", sa.Text(), nullable=True))
    op.create_index("ix_asset_licenses_project_id", "asset_licenses", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_licenses_project_id", "asset_licenses")
    op.drop_column("asset_licenses", "query")
    op.drop_column("asset_licenses", "project_id")
