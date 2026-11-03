"""The Ziro logo is now used in videos: its "#1" tagline is an approved fact (D-35).

Revision ID: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
ASSET = "templates/brand/ziro-digital-logo-transparent.png"
USED = ("Ziro's own brand asset, from ziro.digital; used unaltered on every end card. Its tagline "
        "'#1 AI Career Intelligence Platform' is an approved fact (Dolender, D-35)")
UNUSED = ("Ziro's own brand asset, from ziro.digital (not used in videos yet: tagline "
          "'#1 ...' is an unapproved claim, D-26)")


def upgrade() -> None:
    op.execute(sa.text("UPDATE asset_licenses SET license = :text WHERE asset = :asset")
               .bindparams(text=USED, asset=ASSET))


def downgrade() -> None:
    op.execute(sa.text("UPDATE asset_licenses SET license = :text WHERE asset = :asset")
               .bindparams(text=UNUSED, asset=ASSET))
