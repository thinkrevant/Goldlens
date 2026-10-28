"""Today's alerts and the fact sheet handed to the AI analyst.

Quiet by design: a pair only alerts when the gap is statistically unusual, both legs
traded properly, and reverting to normal would pay more than the round-trip costs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import BacktestConfig, _signal
from .config import LEG_GRAMS, SPECS

COST_MARGIN = 1.5  # expected edge must beat round-trip costs by this factor


def pair_alert(pf: pd.DataFrame, cfg: BacktestConfig) -> dict:
    a, b = pf.attrs["a"], pf.attrs["b"]
    sig = _signal(pf, cfg)
    x = sig["spread"]
    past = x.shift(1).rolling(cfg.window, min_periods=cfg.window // 2)
    stats = pd.DataFrame({"spread": x, "mean": past.mean(), "std": past.std(), "z": sig["z"]})
    last = pf.iloc[-1]
    row = stats.iloc[-1]
    sa, sb = SPECS[a], SPECS[b]
    lots_a, lots_b = LEG_GRAMS / sa.lot_grams, LEG_GRAMS / sb.lot_grams
    notional = last["px10_a"] * LEG_GRAMS / 10.0
    rt_cost = 0.0
    for side in (1, -1):  # open then close
        rt_cost += cfg.costs.leg_cost(sa, last["close_a"], lots_a, side)
        rt_cost += cfg.costs.leg_cost(sb, last["close_b"], lots_b, -side)
    liquid = bool(last["traded_a"] and last["traded_b"]
                  and last["volume_a"] >= cfg.min_volume and last["volume_b"] >= cfg.min_volume)
    z = float(row["z"]) if pd.notna(row["z"]) else np.nan
    edge_bps = abs(row["spread"] - row["mean"]) if pd.notna(row["spread"]) else np.nan
    edge_rs = edge_bps / 1e4 * notional if pd.notna(edge_bps) else np.nan
    flagged = pd.notna(z) and abs(z) >= cfg.entry_z
    passes = bool(flagged and liquid and edge_rs >= COST_MARGIN * rt_cost)
    if not liquid:
        status = "Illiquid: no signal"
    elif passes:
        status = "ALERT"
    elif flagged:
        status = "Flagged, below cost"
    else:
        status = "Normal"
    rich = a if (pd.notna(z) and z > 0) else b
    cheap = b if rich == a else a
    return {
        "pair": f"{a}/{b}", "a": a, "b": b, "as_of": pf.index[-1].date().isoformat(),
        "leg_a": last["contract_a"], "leg_b": last["contract_b"],
        "spread_bps": float(row["spread"]) if pd.notna(row["spread"]) else None,
        "mean_bps": float(row["mean"]) if pd.notna(row["mean"]) else None,
        "std_bps": float(row["std"]) if pd.notna(row["std"]) else None,
        "z": z, "rich": rich if flagged else None, "cheap": cheap if flagged else None,
        "edge_rs": float(edge_rs) if pd.notna(edge_rs) else None,
        "round_trip_cost_rs": float(rt_cost), "liquid": liquid,
        "volume_a": float(last["volume_a"]), "volume_b": float(last["volume_b"]),
        "passes_cost_check": passes, "status": status,
    }


def alerts(pairs: dict, cfg: BacktestConfig) -> list[dict]:
    out = [pair_alert(pf, cfg) for pf in pairs.values()]
    order = {"ALERT": 0, "Flagged, below cost": 1, "Normal": 2, "Illiquid: no signal": 3}
    return sorted(out, key=lambda r: (order[r["status"]], -abs(r["z"]) if r["z"] == r["z"] else 0))


def fact_sheet(curves: pd.DataFrame, alert_rows: list[dict], honest: dict,
               ladder: list[tuple[str, dict]] | None = None) -> dict:
    """Compact JSON-able summary of everything the dashboard shows."""
    c = curves.dropna(subset=["carry"])
    last = c.iloc[-1]
    month_ago = c[c.index <= c.index[-1] - pd.Timedelta(days=30)]
    chg = (last["spot_implied"] / month_ago["spot_implied"].iloc[-1] - 1) * 100 if len(month_ago) else None
    prem = {k.replace("premium_", ""): round(float(v), 1)
            for k, v in last.items() if k.startswith("premium_") and pd.notna(v)}
    facts = {
        "as_of": c.index[-1].date().isoformat(),
        "units": "prices in Rs per 10 g of 999 gold; spreads in bps",
        "market": {"spot_implied": round(float(last["spot_implied"]), 0),
                   "carry_pct": round(float(last["carry"]) * 100, 2),
                   "spot_change_30d_pct": round(chg, 2) if chg is not None else None},
        "premiums_bps": prem,
        "premium_reference": "GOLDM (carry-adjusted)",
        "alerts": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in a.items()}
                   for a in alert_rows],
        "backtest_honest": {k: round(v, 2) if isinstance(v, float) else v for k, v in honest.items()},
    }
    if ladder:
        facts["backtest_ladder_net_pnl"] = {name: round(t["net_pnl"], 0) for name, t in ladder}
    return facts
