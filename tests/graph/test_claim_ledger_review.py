"""Claim ledger end to end: research writes `sources`; per-claim edits at research_review reach the
package; an unsourced claim blocks the script and the reviewer's decision is retained (brief §08).
"""

import json
import os
from pathlib import Path

from conftest import approve, create, status
from sqlalchemy import select

from app.core import db
from app.core.models import Source


def _package(run: dict) -> dict:
    key = next(a["storage_path"] for a in run["artifacts"] if a["type"] == "content_package.json")
    return json.loads((Path(os.environ["RUNS_DIR"]) / key).read_text(encoding="utf-8"))


def test_research_writes_the_ledger(client) -> None:
    project_id = create(client)
    with db.session() as s:
        sources = s.scalars(select(Source).where(Source.project_id == project_id)).all()
    assert len(sources) == 4 and all(src.url.startswith("https://") for src in sources)


def test_claim_edit_reaches_the_package(client) -> None:
    project_id = create(client)
    edited = "IBM defines a chatbot as software that talks with people by text or voice."
    assert approve(client, project_id, edited_claims={"C2": edited}).status_code == 202

    run = status(client, project_id)
    assert run["status"] == "script_review"
    claims = {c["id"]: c["claim"] for c in _package(run)["claims"]}
    assert claims["C2"] == edited
    assert run["approvals"][0]["claim_edits"] == {"removed": [], "edited": {"C2": edited}}


def test_unknown_claim_ids_are_refused(client) -> None:
    project_id = create(client)
    assert approve(client, project_id, removed_claims=["C99"]).status_code == 422


def test_unsourced_claim_blocks_script_and_keeps_decision(client) -> None:
    """Removing C1 leaves the script citing an unapproved claim: scripting fails after its
    revisions, nothing reaches script_review, and the research_review decision stays recorded."""
    project_id = create(client)
    assert approve(client, project_id, removed_claims=["C1"]).status_code == 202

    run = status(client, project_id)
    assert run["status"] == "failed"
    scripting = [j for j in run["jobs"] if j["stage"] == "scripting"]
    assert len(scripting) == 1 and "[C1] is not an approved claim" in scripting[0]["error_message"]
    assert run["approvals"][0]["claim_edits"]["removed"] == ["C1"]
    assert not any(a["stage"] == "scripting" for a in run["artifacts"])
