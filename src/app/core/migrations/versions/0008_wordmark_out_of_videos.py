"""The presenter zone no longer shows the wordmark; the logo appears only on the end card (D-57).

Revision ID: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
ASSET = "templates/brand/ziro-wordmark-only.png"
NOW = "Ziro's own brand asset; not used in videos (D-57: the logo appears only on the end card)"
BEFORE = "Ziro's own brand asset; used unaltered in the presenter-zone placeholder (D-48)"


def upgrade() -> None:
    op.execute(sa.text("UPDATE asset_licenses SET license = :text WHERE asset = :asset")
               .bindparams(text=NOW, asset=ASSET))


def downgrade() -> None:
    op.execute(sa.text("UPDATE asset_licenses SET license = :text WHERE asset = :asset")
               .bindparams(text=BEFORE, asset=ASSET))
