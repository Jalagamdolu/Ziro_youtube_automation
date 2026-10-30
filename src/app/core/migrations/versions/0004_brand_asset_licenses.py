"""Asset-license ledger: Ziro logo and the two brand fonts (D-26).

Revision ID: 0004
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"

ROWS = [
    {"asset": "templates/brand/ziro-digital-logo-transparent.png", "type": "logo",
     "source": "https://ziro.digital/__l5e/assets-v1/b3217b6b-0889-4ee0-9568-834aaf8956b0/"
               "ziro-digital-logo-transparent.png",
     "license": "Ziro's own brand asset, from ziro.digital (not used in videos yet: tagline "
                "'#1 ...' is an unapproved claim, D-26)",
     "proof_url": "https://ziro.digital/"},
    {"asset": "Inter (font, @fontsource/inter 5.3.0)", "type": "font",
     "source": "https://www.npmjs.com/package/@fontsource/inter", "license": "OFL-1.1",
     "proof_url": "https://github.com/rsms/inter/blob/master/LICENSE.txt"},
    {"asset": "Space Grotesk (font, @fontsource/space-grotesk 5.3.0)", "type": "font",
     "source": "https://www.npmjs.com/package/@fontsource/space-grotesk", "license": "OFL-1.1",
     "proof_url": "https://github.com/floriankarsten/space-grotesk/blob/master/OFL.txt"},
]


def upgrade() -> None:
    licenses = sa.table("asset_licenses", sa.column("asset"), sa.column("type"),
                        sa.column("source"), sa.column("license"), sa.column("proof_url"),
                        sa.column("created_at"))
    op.bulk_insert(licenses, [row | {"created_at": datetime.now(UTC)} for row in ROWS])


def downgrade() -> None:
    for row in ROWS:
        op.execute(sa.text("DELETE FROM asset_licenses WHERE asset = :asset")
                   .bindparams(asset=row["asset"]))
