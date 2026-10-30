"""Asset-license ledger: the prototype narration voice (D-23, provisional).

Revision ID: 0003
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"

ASSET = "Kokoro-82M v1.0 voice hf_alpha (kokoro-v1.0.onnx + voices-v1.0.bin) - PROVISIONAL, D-23"


def upgrade() -> None:
    licenses = sa.table("asset_licenses", sa.column("asset"), sa.column("type"),
                        sa.column("source"), sa.column("license"), sa.column("proof_url"),
                        sa.column("created_at"))
    op.bulk_insert(licenses, [{
        "asset": ASSET,
        "type": "tts-voice",
        "source": "https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0",
        "license": "Apache-2.0 (weights; trained on permissive/public-domain audio)",
        "proof_url": "https://huggingface.co/hexgrad/Kokoro-82M",
        "created_at": datetime.now(UTC),
    }])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM asset_licenses WHERE asset = :asset").bindparams(asset=ASSET))
