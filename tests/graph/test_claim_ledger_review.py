"""Claim ledger end to end: research writes `sources`; an unsourced claim blocks the script
(brief §08). Since v2 the claims are reviewed with the script at script_review (D-50).
"""

from conftest import create, status
from sqlalchemy import select

from app.adapters import research
from app.core import db
from app.core.models import Source


def test_research_writes_the_ledger(client) -> None:
    project_id = create(client)
    with db.session() as s:
        sources = s.scalars(select(Source).where(Source.project_id == project_id)).all()
    assert len(sources) == 4 and all(src.url.startswith("https://") for src in sources)


def test_unsourced_claim_blocks_script(client, monkeypatch) -> None:
    """Research without C1 leaves the script citing an unapproved claim: scripting fails after
    its revisions and nothing reaches script_review."""
    found = research.FixtureResearch.find_claims
    monkeypatch.setattr(research.FixtureResearch, "find_claims",
                        lambda self, brief: [c for c in found(self, brief) if c.id != "C1"])
    project_id = create(client)

    run = status(client, project_id)
    assert run["status"] == "failed"
    scripting = [j for j in run["jobs"] if j["stage"] == "scripting"]
    assert len(scripting) == 1 and "[C1] is not an approved claim" in scripting[0]["error_message"]
    assert not any(a["stage"] == "scripting" for a in run["artifacts"])
