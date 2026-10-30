"""T01: topic, audience, language, CTA and duration persist and appear in generated outputs."""

import json
import os
from pathlib import Path

from conftest import DISCLOSURE, SHORT_TOPIC, approve, create, run_to_qa_review, status

BRIEF = {
    "prompt": SHORT_TOPIC,
    "format": "short",
    "audience": "Final-year engineering students",
    "language": "en",
    "cta": "Find project guides at ziro.digital",
    "target_seconds": 50,
}


def _read(key: str) -> dict:
    return json.loads((Path(os.environ["RUNS_DIR"]) / key).read_text(encoding="utf-8"))


def test_brief_fields_persist_into_outputs(client) -> None:
    project_id = run_to_qa_review(client, **BRIEF)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    run = status(client, project_id)

    assert run["brief"] == {"topic": SHORT_TOPIC, "audience": BRIEF["audience"], "language": "en",
                            "format": "short", "target_seconds": 50, "cta": BRIEF["cta"]}

    paths = {a["type"]: a["storage_path"] for a in run["artifacts"]}
    brief = _read(paths["brief.json"])
    package = _read(paths["content_package.json"])
    receipt = _read(paths["publish_receipt.json"])
    assert brief["audience"] == BRIEF["audience"] and brief["target_seconds"] == 50
    assert package["brief"] == brief
    assert BRIEF["cta"] in package["script"] and BRIEF["cta"] in package["description"]
    assert BRIEF["cta"] in receipt["request"]["snippet"]["description"]
    assert receipt["request"]["snippet"]["defaultLanguage"] == "en"


def test_prototype_mode_fails_clearly_without_a_fixture(client) -> None:
    """D-19: a topic without a fixture stops at researching with a clear reason, no fake content."""
    project_id = create(client, prompt="A topic with no prototype fixture")
    run = status(client, project_id)
    assert run["status"] == "failed"
    research = [j for j in run["jobs"] if j["stage"] == "researching"]
    assert "no fixture for this topic in prototype mode" in research[-1]["error_message"]
    assert not any(a["stage"] == "scripting" for a in run["artifacts"])
