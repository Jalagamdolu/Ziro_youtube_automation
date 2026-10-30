"""T01: topic, audience, language, CTA and duration persist and appear in generated outputs."""

import json
import os
from pathlib import Path

from conftest import DISCLOSURE, approve, run_to_qa_review, status

BRIEF = {
    "prompt": "Three practical GenAI portfolio projects for freshers",
    "format": "long",
    "audience": "Final-year engineering students",
    "language": "en",
    "cta": "Find project guides at ziro.digital",
    "target_seconds": 200,
}


def _read(key: str) -> dict:
    return json.loads((Path(os.environ["RUNS_DIR"]) / key).read_text(encoding="utf-8"))


def test_brief_fields_persist_into_outputs(client) -> None:
    project_id = run_to_qa_review(client, **BRIEF)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    run = status(client, project_id)

    assert run["brief"] == {"topic": BRIEF["prompt"], "audience": BRIEF["audience"],
                            "language": "en", "format": "long", "target_seconds": 200,
                            "cta": BRIEF["cta"]}

    paths = {a["type"]: a["storage_path"] for a in run["artifacts"]}
    brief = _read(paths["brief.json"])
    package = _read(paths["content_package.json"])
    receipt = _read(paths["publish_receipt.json"])
    assert brief["topic"] == BRIEF["prompt"] and brief["target_seconds"] == 200
    assert package["brief"] == brief
    assert BRIEF["cta"] in receipt["request"]["snippet"]["description"]
    assert receipt["request"]["snippet"]["defaultLanguage"] == "en"


def test_changed_topic_needs_no_code_change(client) -> None:
    first = run_to_qa_review(client)
    second = run_to_qa_review(client, prompt="A different topic entirely")
    assert status(client, first)["brief"]["topic"] != status(client, second)["brief"]["topic"]
