"""T11: every paid call is a costs row priced from config.yaml; the spend cap is enforced."""

import pytest
from conftest import create

from app.core import config, costs, db
from app.core.errors import FatalError


def test_cost_rows_use_config_prices_and_cap(client, monkeypatch) -> None:
    project_id = create(client)
    cfg = config.load()
    cfg["prices"] = {"anthropic-input-token": 0.000003}
    cfg["spend_cap_usd"] = 1.0

    with db.session() as s, s.begin():
        row = costs.record_cost(s, project_id, "scripting", "anthropic-input-token", 100_000)
        assert row.amount == pytest.approx(0.3)
        assert row.unit_price == 0.000003 and row.observed_or_estimate == "observed"
        assert costs.total(s, project_id) == pytest.approx(0.3)

    with db.session() as s, s.begin(), pytest.raises(FatalError, match="spend cap"):
        costs.record_cost(s, project_id, "scripting", "anthropic-input-token", 1_000_000)
