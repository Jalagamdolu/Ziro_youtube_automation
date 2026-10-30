"""researching: build the claim ledger. Unverified claims are dropped (§4)."""

import json

from sqlalchemy import delete

from app.adapters import research
from app.core import db
from app.core.contracts import Brief
from app.core.errors import FatalError
from app.core.log import log
from app.core.models import Source
from app.nodes.context import Outputs, StageContext


def researching(ctx: StageContext) -> Outputs:
    brief = Brief.model_validate(ctx.read_json("draft", "brief.json"))
    found = research.get().find_claims(brief)
    claims = [c for c in found if c.verification_status == "verified"]
    if len(claims) < len(found):
        log.warning("dropped unverified claims", dropped=len(found) - len(claims))
    if not claims:
        raise FatalError("research found no verified claims")

    with db.session() as s, s.begin():
        s.execute(delete(Source).where(Source.project_id == ctx.project_id))  # ledger = latest run
        s.add_all(Source(project_id=ctx.project_id, url=c.url, title=c.title,
                         accessed_at=c.accessed_at, published_at=c.published_at, claim=c.claim,
                         verification_status=c.verification_status) for c in claims)
    return {"claims.json": json.dumps([c.model_dump(mode="json") for c in claims], indent=2,
                                      ensure_ascii=False)}
