"""Phase 1 stub stages: write fake but contract-valid artifacts so the full graph runs end to end.

Each later phase replaces one entry in app.nodes.FUNCS with the real stage.
"""

import json
from datetime import UTC, datetime

from app.adapters.publisher import MockPublisher, approved_run
from app.core import costs, db
from app.core.contracts import Brief, Chapter, Claim, ContentPackage, Hook
from app.nodes.context import StageContext

Outputs = dict[str, str | bytes]

STUB_URL = "https://example.com/stub-source"


def _dump(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def draft(ctx: StageContext) -> Outputs:
    request = json.loads(ctx.storage.read(f"{ctx.project_id}/request.json"))
    brief = Brief.model_validate(request["brief"])
    return {"brief.json": brief.model_dump_json(indent=2)}


def researching(ctx: StageContext) -> Outputs:
    brief = Brief.model_validate(ctx.read_json("draft", "brief.json"))
    claim = Claim(
        id="C1",
        claim=f"Stub claim about {brief.topic}",
        url=STUB_URL,
        title="Stub source",
        quote="stub quote",
        accessed_at=datetime.now(UTC),
        verification_status="verified",
    )
    return {"claims.json": _dump([claim.model_dump(mode="json")])}


def scripting(ctx: StageContext) -> Outputs:
    brief = Brief.model_validate(ctx.read_json("draft", "brief.json"))
    claims = [Claim.model_validate(c) for c in ctx.read_json("researching", "claims.json")]
    script = f"[ON SCREEN] {brief.topic}\nStub narration citing [C1].\n{brief.cta}\n"
    if ctx.notes:
        script += f"<!-- revised for: {ctx.notes} -->\n"
    package = ContentPackage(
        brief=brief,
        claims=claims,
        script=script,
        hooks=[Hook(text=f"Stub hook {i}", score=float(i), explanation="stub") for i in range(5)],
        titles=[f"Stub title {i}" for i in range(10)],
        top_titles=[f"Stub title {i}" for i in range(3)],
        thumbnail_text="Stub thumbnail",
        description=f"{brief.topic}\n\n{brief.cta}",
        tags=["stub"],
        target_queries=["stub query 1", "stub query 2", "stub query 3"],
        chapters=[Chapter(start_seconds=0, title="Intro")],
    )
    return {"script.md": script, "content_package.json": package.model_dump_json(indent=2)}


def storyboarding(ctx: StageContext) -> Outputs:
    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    scene = {
        "id": "S1",
        "text": package.script,
        "visual_type": "title",
        "asset": None,
        "duration": package.brief.target_seconds,
    }
    return {"scenes.json": _dump([scene])}


def rendering(ctx: StageContext) -> Outputs:
    scenes = ctx.read_json("storyboarding", "scenes.json")
    return {
        "video.mp4": b"STUB VIDEO",
        "captions.srt": "1\n00:00:00,000 --> 00:00:02,000\nStub caption\n",
        "thumbnail.png": b"STUB PNG",
        "qa_report.json": _dump({"passed": True, "stub": True, "scenes": len(scenes),
                                 "notes": ctx.notes}),
    }


def export_ready(ctx: StageContext) -> Outputs:
    return {"manifest.json": _dump({"artifacts": ctx.inputs})}


def mock_published(ctx: StageContext) -> Outputs:
    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    request = {
        "snippet": {
            "title": package.top_titles[0],
            "description": package.description,
            "tags": package.tags,
            "categoryId": "27",
            "defaultLanguage": package.brief.language,
        },
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    }
    with db.session() as s, s.begin():
        row = MockPublisher().publish(s, approved_run(s, ctx.project_id), request)
        receipt = {"request": request, "video_id": row.provider_video_id,
                   "idempotency_key": row.idempotency_key, "mocked": True}
    return {"publish_receipt.json": _dump(receipt)}


def metrics_stub(ctx: StageContext) -> Outputs:
    metrics = {
        "source": "stub",
        "columnHeaders": ["views", "estimatedMinutesWatched", "averageViewDuration",
                          "averageViewPercentage", "subscribersGained"],
        "rows": [[0, 0, 0, 0, 0]],
    }
    with db.session() as s:
        total = costs.total(s, ctx.project_id)
    return {"metrics.json": _dump(metrics), "cost_report.json": _dump({"total_usd": total})}
