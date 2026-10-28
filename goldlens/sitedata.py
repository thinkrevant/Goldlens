"""Real GoldLens numbers for the landing page (served as /data.js, or exported to site/data.js)."""
from __future__ import annotations

import datetime

import numpy as np

from . import notify, tipcheck
from .backtest import BacktestConfig, attribution, ladder_configs, run_portfolio
from .config import SYMBOLS
from .pipeline import daily_facts


def r(x, d=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)


def build_site_data(ws) -> dict:
    """Everything the landing page animates, from the live workspace."""
    rows, honest, facts = daily_facts(ws)

    # 1. Four quoted prices vs one normalised scale, last ~12 months, every 2nd trading day
    fr = ws.front.reset_index()
    fr = fr[fr["date"] >= fr["date"].max() - datetime.timedelta(days=365)]
    dates = sorted(fr["date"].unique())[::2]
    series = {"dates": [str(d)[:10] for d in dates]}
    for sym in SYMBOLS:
        s = fr[fr["symbol"] == sym].set_index("date").reindex(dates).ffill().bfill()
        series[sym] = {"quoted": [r(v, 0) for v in s["close"]], "px10": [r(v, 0) for v in s["px10"]]}
        last_row = ws.front.xs(sym, level="symbol").iloc[-1]
        series[sym]["day_chg"] = r((last_row["close"] / last_row["prev_close"] - 1) * 100) if last_row["prev_close"] else 0.0

    # 2. Honesty ladder over all pairs
    ladder = []
    for name, cfg in ladder_configs(BacktestConfig()):
        daily, _, tot = run_portfolio(ws.pairs, cfg, ws.prices)
        ladder.append({"name": name, "net": r(tot["net_pnl"], 0), "trades": tot["trades"], "costs": r(tot["costs"], 0)})
        if name == "Naive":
            naive_daily = daily["total"]
        last_daily = daily["total"]
    gold = ws.front.xs("GOLDM", level="symbol")["px10"]
    a_naive, a_honest = attribution(naive_daily, gold), attribution(last_daily, gold)

    # 3. Best pair after costs
    _, results, _ = run_portfolio(ws.pairs, BacktestConfig(), ws.prices)
    best_key, best = max(results.items(), key=lambda kv: kv[1].metrics["net_pnl"])

    # 4. Tip Checker on the headline example
    rule = tipcheck.parse_rules(tipcheck.EXAMPLES[0])
    ev = tipcheck.evaluate(rule, ws)

    # 5. Premium story: monthly median premium vs GOLDM
    prem = ws.curves[[f"premium_{s}" for s in ("GOLDGUINEA", "GOLDPETAL")]].resample("ME").median()
    premiums = {"months": [d.strftime("%b %y") for d in prem.index],
                "GOLDGUINEA": [r(v, 0) for v in prem["premium_GOLDGUINEA"]],
                "GOLDPETAL": [r(v, 0) for v in prem["premium_GOLDPETAL"]]}

    morning, _ = notify.build_morning(ws, rows, facts, use_ai=False)

    data = {
        "generated": datetime.date.today().isoformat(),
        "meta": {"trading_days": int(ws.df["date"].nunique()), "first": str(ws.df["date"].min())[:10],
                 "last": str(ws.df["date"].max())[:10], "contracts": int(ws.df["contract"].nunique()),
                 "pairs": len(ws.pairs)},
        "market": facts["market"], "premiums_now": facts.get("premiums_bps", {}),
        "series": series,
        "ladder": ladder,
        "attribution": {"naive_g": r(a_naive["beta_grams"], 0), "naive_r2": r(a_naive["r2"]),
                        "honest_g": r(a_honest["beta_grams"], 0), "honest_r2": r(a_honest["r2"])},
        "best_pair": {"pair": "/".join(best_key), "net": r(best.metrics["net_pnl"], 0),
                      "trades": best.metrics["trades"], "win_rate": r(best.metrics["win_rate"] * 100, 0)},
        "tip": {"text": tipcheck.EXAMPLES[0], "rule": rule.describe(), "claimed": rule.claimed_annual_pct,
                "naive_ann": r(ev["naive"]["ann_pct"], 1), "honest_ann": r(ev["honest"]["ann_pct"], 1),
                "trades": ev["honest"]["trades"], "verdict": ev["verdict"][1], "detail": ev["verdict"][2],
                "flags": rule.red_flags,
                "breakdown": [{"reason": a, "rs": r(b, 0), "pct": r(c, 0)} for a, b, c in ev["breakdown"]]},
        "premiums": premiums,
        "morning_html": morning,
    }
    return data
