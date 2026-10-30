"""Research adapter. Prototype mode returns a fixture claim ledger whose URLs and quotes were
checked by hand against the live pages (D-19); the production agent loop (search → fetch →
verify) is not built until the user switches to production mode.
"""

import json
from typing import Protocol

from app.adapters.llm import fixture_dir
from app.core import config
from app.core.contracts import Brief, Claim
from app.core.errors import FatalError


class Research(Protocol):
    def find_claims(self, brief: Brief) -> list[Claim]: ...


class FixtureResearch:
    def find_claims(self, brief: Brief) -> list[Claim]:
        raw = json.loads((fixture_dir(brief.topic) / "claims.json").read_text(encoding="utf-8"))
        return [Claim.model_validate(c) for c in raw]


def get() -> Research:
    if config.load()["mode"] == "prototype":
        return FixtureResearch()
    raise FatalError("production research agent is not built yet (D-19)")
