from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import config, db
from app.core.errors import FatalError
from app.core.models import Cost


def record_cost(
    s: Session,
    project_id: str,
    stage: str,
    provider: str,
    units: float,
    observed: bool = True,
) -> Cost:
    """Record one paid call at its config.yaml unit price; refuse once the spend cap is passed."""
    cfg: dict[str, Any] = config.load()
    unit_price = float(cfg["prices"][provider])
    cost = Cost(
        project_id=project_id,
        stage=stage,
        provider=provider,
        units=units,
        unit_price=unit_price,
        amount=units * unit_price,
        observed_or_estimate="observed" if observed else "estimate",
    )
    s.add(cost)
    s.flush()
    if total(s, project_id) > cfg["spend_cap_usd"]:
        raise FatalError(f"spend cap {cfg['spend_cap_usd']} USD exceeded")
    return cost


class BudgetExceeded(FatalError):
    """A paid call would pass the per-run token cap or the daily spend cap (D-45)."""


def check_budget(project_id: str | None, tokens: float, usd: float,
                 pending: list[tuple[str, float]]) -> None:
    """Refuse a paid call before it is made when it would pass a config.yaml budget cap.
    `tokens`/`usd` are the call's worst case; `pending` is usage this stage has not recorded
    yet."""
    cfg: dict[str, Any] = config.load()
    caps, prices = cfg["budget"], cfg["prices"]
    pending_tokens = sum(units for key, units in pending if key.startswith("claude-"))
    pending_usd = sum(units * float(prices[key]) for key, units in pending)
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with db.session() as s:
        today = float(s.scalar(select(func.coalesce(func.sum(Cost.amount), 0.0))
                               .where(Cost.created_at >= midnight)) or 0.0)
        used = float(s.scalar(select(func.coalesce(func.sum(Cost.units), 0.0)).where(
            Cost.project_id == project_id, Cost.provider.startswith("claude-"))) or 0.0
        ) if project_id else 0.0
    if used + pending_tokens + tokens > caps["max_tokens_per_run"]:
        raise BudgetExceeded(
            f"budget: this call could take the run to {used + pending_tokens + tokens:,.0f} "
            f"Claude tokens, over the per-run cap of {caps['max_tokens_per_run']:,} "
            "(config.yaml budget.max_tokens_per_run)")
    if today + pending_usd + usd > caps["max_usd_per_day"]:
        raise BudgetExceeded(
            f"budget: today's spend would reach ${today + pending_usd + usd:.2f}, over the daily "
            f"cap of ${caps['max_usd_per_day']:.2f} (config.yaml budget.max_usd_per_day). "
            "Retry tomorrow or raise the cap.")


def total(s: Session, project_id: str) -> float:
    return float(s.scalar(select(func.coalesce(func.sum(Cost.amount), 0.0)).where(
        Cost.project_id == project_id
    )) or 0.0)


def record_usage(project_id: str, stage: str, calls: list[tuple[str, float]]) -> None:
    """One row per (price key, units) an adapter used; free-tier calls cost $0 but keep their
    token counts for the paid estimate."""
    if not calls:
        return
    with db.session() as s, s.begin():
        for provider, units in calls:
            record_cost(s, project_id, stage, provider, units)
