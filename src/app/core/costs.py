from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import config
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


def total(s: Session, project_id: str) -> float:
    return float(s.scalar(select(func.coalesce(func.sum(Cost.amount), 0.0)).where(
        Cost.project_id == project_id
    )) or 0.0)
