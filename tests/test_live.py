import numpy as np
import pandas as pd
import pytest

from goldlens import live
from goldlens.backtest import BacktestConfig

SAMPLE_INSTRUMENT = {
    "segment": "MCX_FO", "exchange": "MCX", "expiry": 1793384999000, "instrument_type": "FUT",
    "underlying_symbol": "GOLDGUINEA", "instrument_key": "MCX_FO|571305", "lot_size": 8,
    "trading_symbol": "GOLDGUINEA FUT 30 OCT 26",
}


def test_parse_instruments_converts_expiry_to_ist_date():
    df = live.parse_instruments([SAMPLE_INSTRUMENT, {**SAMPLE_INSTRUMENT, "underlying_symbol": "SILVERM"}])
    assert len(df) == 1
    assert df.loc[0, "expiry"] == pd.Timestamp("2026-10-30")
    assert df.loc[0, "instrument_key"] == "MCX_FO|571305"


def test_parse_quotes_reads_book_and_trade_time():
    data = {"MCX_FO:GOLDGUINEA26OCTFUT": {
        "instrument_token": "MCX_FO|571305", "last_price": 118009.0, "volume": 7252, "oi": 13938,
        "last_trade_time": "1792333758000",
        "depth": {"buy": [{"price": 118000.0, "quantity": 3, "orders": 1}],
                  "sell": [{"price": 118020.0, "quantity": 2, "orders": 1}]}}}
    q = live.parse_quotes(data).iloc[0]
    assert q["bid"] == 118000.0 and q["ask"] == 118020.0
    assert q["last_trade_time"].tz is not None


def test_no_token_falls_back_to_daily(monkeypatch):
    monkeypatch.delenv("UPSTOX_ANALYTICS_TOKEN", raising=False)
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    snap = live.snapshot()
    assert not snap.ok and snap.source == "daily"
    assert "UPSTOX_ANALYTICS_TOKEN" in snap.message


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_rejected_token_raises_clear_error(monkeypatch):
    monkeypatch.setattr(live.requests, "get", lambda *a, **k: _Resp(401))
    with pytest.raises(live.LiveDataError, match="401"):
        live.fetch_quotes(["MCX_FO|1"], "bad-token")


def test_api_failure_never_raises_from_snapshot(monkeypatch):
    monkeypatch.setattr(live, "load_instruments", lambda: live.parse_instruments([SAMPLE_INSTRUMENT]))
    monkeypatch.setattr(live.requests, "get", lambda *a, **k: _Resp(500))
    snap = live.snapshot(token="x")
    assert not snap.ok and "HTTP 500" in snap.message


@pytest.fixture(scope="module")
def ws():
    from goldlens.config import PANEL_PATH
    if not PANEL_PATH.exists():
        pytest.skip("no cached MCX panel")
    from goldlens.pipeline import build_workspace
    return build_workspace()


def _fake_market(ws, fresh=True):
    """Instruments + quotes built from the last settlement, so prices are realistic."""
    last = ws.df[ws.df["date"] == ws.df["date"].max()]
    inst = pd.DataFrame({"symbol": last["symbol"], "instrument_key": [f"MCX_FO|{i}" for i in range(len(last))],
                         "trading_symbol": last["contract"], "expiry": last["expiry"], "lot_size": 1})
    now = pd.Timestamp.now(tz=live.IST)
    ltt = now if fresh else now - pd.Timedelta(days=2)
    quotes = pd.DataFrame({"instrument_key": inst["instrument_key"], "last_price": last["close"].to_numpy(),
                           "bid": last["close"].to_numpy() - 2, "ask": last["close"].to_numpy() + 2,
                           "volume": last["volume"].to_numpy() + 100, "oi": last["oi"].to_numpy(),
                           "last_trade_time": ltt})
    return inst.reset_index(drop=True), quotes


@pytest.mark.parametrize("fresh", [True, False])
def test_live_alerts_end_to_end(ws, monkeypatch, fresh):
    inst, quotes = _fake_market(ws, fresh)
    monkeypatch.setattr(live, "load_instruments", lambda: inst)
    monkeypatch.setattr(live, "fetch_quotes", lambda keys, token: quotes)
    snap = live.snapshot(ws.roll_bdays, token="x")
    assert snap.ok and snap.stale is (not fresh)
    rows = live.live_alerts(snap, ws.pairs, ws.curves, BacktestConfig(), ws.roll_bdays)
    assert len(rows) == len(ws.pairs)
    for r in rows:
        assert np.isfinite(r["z"]) and r["round_trip_cost_rs"] > 0
        # a 4-rupee-wide book must cost at least the book crossing
        assert r["book_cost_rs"] > 0
        if not fresh:
            assert r["status"] == "Market closed" and not r["passes_cost_check"]
