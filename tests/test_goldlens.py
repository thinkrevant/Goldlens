from datetime import date

import numpy as np
import pandas as pd
import pytest

from goldlens.analytics import zscore
from goldlens.backtest import BacktestConfig, _targets, run_pair
from goldlens.config import SPECS, CostModel
from goldlens.ingest import validate_day
from goldlens.normalise import normalise


def test_normalisation_factors():
    assert SPECS["GOLDTEN"].to_base == pytest.approx(1.0)
    assert SPECS["GOLDGUINEA"].to_base == pytest.approx(10 / 8)
    assert SPECS["GOLDPETAL"].to_base == pytest.approx(10.0)
    assert SPECS["GOLDM"].to_base == pytest.approx(999 / 995)


def test_rupees_per_point():
    # GOLDM: 100 g lot quoted per 10 g -> Rs 10 per Rs 1 move
    assert SPECS["GOLDM"].rupees_per_point == 10
    assert SPECS["GOLDGUINEA"].rupees_per_point == 1
    assert SPECS["GOLDPETAL"].rupees_per_point == 1


def test_normalise_puts_contracts_on_one_scale():
    d, e = pd.Timestamp("2026-10-06"), pd.Timestamp("2026-10-30")
    panel = pd.DataFrame({
        "date": [d] * 3, "symbol": ["GOLDTEN", "GOLDGUINEA", "GOLDPETAL"], "expiry": [e] * 3,
        "close": [149288.0, 119957.0, 14992.0], "volume": [1, 1, 1], "traded": [True] * 3,
    })
    out = normalise(panel).set_index("symbol")["px10"]
    assert out["GOLDGUINEA"] == pytest.approx(149946.25)
    assert out["GOLDPETAL"] == pytest.approx(149920.0)
    # after normalising, all three sit within 0.5% of each other
    assert out.max() / out.min() - 1 < 0.005


def test_validate_day_rejects_wrong_date_and_flags_holidays():
    day = date(2026, 10, 16)
    good = [{"Date": "10/16/2026", "Symbol": "GOLDM     "}, {"Date": "10/16/2026", "Symbol": "SILVER"}]
    status, rows = validate_day(day, good)
    assert status == "ok" and len(rows) == 1
    assert validate_day(day, None)[0] == "holiday"
    assert validate_day(day, [])[0] == "holiday"
    stale = [{"Date": "10/15/2026", "Symbol": "GOLDM"}]
    assert validate_day(day, stale)[0] == "rejected"


def test_cost_model():
    spec = SPECS["GOLDM"]
    assert CostModel.zero().leg_cost(spec, 150000, 2, 1) == 0
    c = CostModel()
    buy, sell = c.leg_cost(spec, 150000, 2, 1), c.leg_cost(spec, 150000, 2, -1)
    assert sell > buy  # CTT on the sell side outweighs stamp duty on the buy side
    assert c.leg_cost(spec, 150000, 0, 1) == 0


def test_zscore_uses_only_the_past():
    x = pd.Series(np.random.default_rng(0).normal(size=200))
    z_full = zscore(x, 30)
    changed = x.copy()
    changed.iloc[150:] += 100  # rewrite the future
    z_changed = zscore(changed, 30)
    pd.testing.assert_series_equal(z_full.iloc[:150], z_changed.iloc[:150])


def test_targets_hysteresis():
    cfg = BacktestConfig(entry_z=2, exit_z=0.5, max_hold=99)
    z = pd.Series([0, 2.5, 1.5, 0.8, 0.3, -2.4, -1.0, -0.2])
    assert list(_targets(z, cfg)) == [0, -1, -1, -1, 0, 1, 1, 0]


@pytest.fixture(scope="module")
def ws():
    from goldlens.config import PANEL_PATH
    if not PANEL_PATH.exists():
        pytest.skip("no cached MCX panel; run python -m goldlens.ingest first")
    from goldlens.pipeline import build_workspace
    return build_workspace()


def test_backtest_has_no_lookahead(ws):
    """Dropping future data must not change any P&L booked before the cut."""
    key, pf = next(iter(ws.pairs.items()))
    cut = pf.index[int(len(pf) * 0.7)]
    cfg = BacktestConfig()
    full = run_pair(pf, cfg, ws.prices).daily["net"]
    trunc_pf = pf.loc[:cut].copy()
    trunc_pf.attrs.update(pf.attrs)
    trunc = run_pair(trunc_pf, cfg, ws.prices).daily["net"]
    # the truncated run force-closes on its last day, so compare up to the day before
    before = trunc.index[:-1]
    np.testing.assert_allclose(full.loc[before].to_numpy(), trunc.loc[before].to_numpy(), atol=1e-6)


def test_honest_ladder_step_never_has_more_trades_than_cost_free(ws):
    from goldlens.backtest import ladder_configs, run_portfolio
    steps = dict((n, c) for n, c in ladder_configs())
    _, _, no_cost = run_portfolio(ws.pairs, steps["+ real contracts & carry"], ws.prices)
    _, _, with_cost = run_portfolio(ws.pairs, steps["+ costs"], ws.prices)
    assert with_cost["trades"] == no_cost["trades"]
    assert with_cost["net_pnl"] <= no_cost["net_pnl"]
    assert with_cost["costs"] > 0
