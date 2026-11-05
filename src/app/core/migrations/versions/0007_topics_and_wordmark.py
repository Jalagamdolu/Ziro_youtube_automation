"""Topic planner (D-47) and the license rows for the split layout's assets (D-48).

Revision ID: 0007
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"

ROWS = [
    {"asset": "templates/brand/ziro-wordmark-only.png", "type": "logo",
     "source": "Supplied by Ziro (Dolender, 2026-11-05)",
     "license": "Ziro's own brand asset; used unaltered in the presenter-zone placeholder (D-48)",
     "proof_url": "https://ziro.digital/"},
    {"asset": "Playfair Display italic (font, @fontsource/playfair-display 5.2.8)", "type": "font",
     "source": "https://www.npmjs.com/package/@fontsource/playfair-display", "license": "OFL-1.1",
     "proof_url": "https://github.com/clauseggers/Playfair/blob/master/OFL.txt"},
]


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("keywords", sa.JSON, nullable=False),
        sa.Column("guidelines", sa.Text, nullable=False),
        sa.Column("format", sa.String, nullable=False),
        sa.Column("target_seconds", sa.Integer, nullable=True),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id"), nullable=True,
                  index=True),
        sa.Column("created_by", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    licenses = sa.table("asset_licenses", sa.column("asset"), sa.column("type"),
                        sa.column("source"), sa.column("license"), sa.column("proof_url"),
                        sa.column("created_at"))
    op.bulk_insert(licenses, [row | {"created_at": datetime.now(UTC)} for row in ROWS])


def downgrade() -> None:
    for row in ROWS:
        op.execute(sa.text("DELETE FROM asset_licenses WHERE asset = :asset")
                   .bindparams(asset=row["asset"]))
    op.drop_table("topics")
