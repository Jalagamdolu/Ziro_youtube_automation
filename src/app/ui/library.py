"""The Library (D-69): every video as a card with one status chip and only that state's actions.
Videos waiting for one of your reviews are pinned to the top; filters narrow the list. A video
approved at the final review lands here with a "Saved to Library" toast."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.ui import planner
from app.ui.routes import templates

router = APIRouter()


@router.get("/library", response_class=HTMLResponse)
def library(request: Request, show: str = "all", saved: str | None = None,
            error: str | None = None) -> HTMLResponse:
    show = show if show in planner.FILTERS else "all"
    cards = [v for v in planner.videos(saved) if v["project"] is not None]
    counts = {key: sum(1 for c in cards if keys is None or c["key"] in keys)
              for key, (_, keys) in planner.FILTERS.items()}
    keys = planner.FILTERS[show][1]
    shown = [c for c in cards if keys is None or c["key"] in keys]
    shown.sort(key=lambda c: (c["key"] not in ("review_script", "review_video"),
                              c["key"] == "cancelled", -c["created"].timestamp()))
    return templates.TemplateResponse(request, "library.html", {
        "cards": shown, "show": show, "filters": planner.FILTERS, "counts": counts,
        "saved": saved, "pending": any(c["key"] == "saving" for c in shown), "error": error,
        "min_time": planner.local_input(datetime.now(UTC) + timedelta(minutes=5))})
