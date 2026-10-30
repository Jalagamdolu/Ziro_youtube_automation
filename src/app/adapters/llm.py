"""LLM adapter. Prototype mode serves hand-written fixtures (D-19); production (Anthropic SDK, D-02)
is not built until the user switches to production mode.
"""

import json
import re
from pathlib import Path
from typing import Protocol

from app.core import config
from app.core.contracts import Brief, Claim, PackageDraft
from app.core.errors import FatalError

FIXTURES = Path(__file__).parent / "fixtures"


class LLM(Protocol):
    def write_package(self, brief: Brief, claims: list[Claim], notes: str | None) -> PackageDraft:
        """Script, hooks, titles and SEO for a brief, using only `claims`; `notes` asks for a
        revision (reviewer notes or failed checks)."""
        ...


class FixtureLLM:
    def write_package(self, brief: Brief, claims: list[Claim], notes: str | None) -> PackageDraft:
        folder = fixture_dir(brief.topic)
        package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
        package["script"] = (folder / "script.md").read_text(encoding="utf-8")
        # The CTA comes from the brief, as a real model would write it (T01).
        filled = json.loads(json.dumps(package).replace("{cta}", brief.cta))
        return PackageDraft.model_validate(filled)


def fixture_dir(topic: str) -> Path:
    folder = FIXTURES / re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    if not folder.is_dir():
        known = ", ".join(sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()))
        raise FatalError(f"no fixture for this topic in prototype mode (have: {known})")
    return folder


def get() -> LLM:
    if config.load()["mode"] == "prototype":
        return FixtureLLM()
    raise FatalError("production LLM adapter is not built yet (D-19)")
