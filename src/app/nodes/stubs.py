"""Stub stages: fake but contract-valid artifacts so the full graph runs end to end.

Each phase replaces entries in app.nodes.FUNCS with real stages.
"""

import json

from app.adapters.publisher import MockPublisher, approved_run
from app.core import costs, db
from app.core.contracts import ContentPackage
from app.nodes.context import Outputs, StageContext


def _dump(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


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
    footage = f"{ctx.inputs['rendering']}/stock.json"  # D-33: credit the stock provider
    credit = (json.loads(ctx.storage.read(footage)).get("credit")
              if ctx.storage.exists(footage) else None)
    request = {
        "snippet": {
            "title": package.top_titles[0],
            "description": f"{package.description}\n\n{credit}" if credit else package.description,
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
