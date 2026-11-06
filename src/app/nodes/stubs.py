"""Stub stages: fake but contract-valid artifacts so the full graph runs end to end.

Each phase replaces entries in app.nodes.FUNCS with real stages.
"""

import json

from app.adapters import publisher
from app.adapters.publisher import approved_run
from app.core import costs, db, metadata
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
    """The publish step (state name from the brief; the provider follows publish.mode, D-69)."""
    from app.jobs import scheduler

    package = ContentPackage.model_validate(ctx.read_json("scripting", "content_package.json"))
    footage = f"{ctx.inputs['rendering']}/stock.json"  # D-33: credit the stock provider
    credit = (json.loads(ctx.storage.read(footage)).get("credit")
              if ctx.storage.exists(footage) else None)
    provider = publisher.get()
    with db.session() as s, s.begin():
        run = approved_run(s, ctx.project_id)
        meta = metadata.edited(s, ctx.project_id) or {
            "title": package.top_titles[0], "description": package.description,
            "tags": package.tags}
        description = f"{meta['description']}\n\n{credit}" if credit else meta["description"]
        request = publisher.request(run, meta["title"], description, meta["tags"],
                                    package.brief.language, generated=True)
        row = provider.publish(s, run, request, f"{ctx.inputs['rendering']}/video.mp4",
                               scheduler.publish_at(ctx.project_id))
        receipt = {"request": request, "platform": row.platform, "video_id": row.provider_video_id,
                   "idempotency_key": row.idempotency_key, "mocked": row.platform != "youtube",
                   "publish_at": row.scheduled_at}
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
