"""Walk-forward pair backtester with switchable honesty fixes.

Every flag in BacktestConfig removes one common backtest flaw. Running the "ladder"
turns them on one at a time, so you can see how much of a naive edge each flaw creates.

Rule: when the spread z-score passes +entry, short the rich leg and buy the cheap leg
(gram-matched); exit when |z| falls back under `exit_z` or after `max_hold` days.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .analytics import zscore
from .config import LEG_GRAMS, SPECS, CostModel


@dataclass
class BacktestConfig:
    # honesty switches
    gram_matched: bool = True     # size legs by grams, not 1 lot vs 1 lot
    next_day_fill: bool = True    # decide on day T settlement, fill at T+1
    rolling_stats: bool = True    # z-score from past data only
    true_contracts: bool = True   # P&L on held contracts + carry-adjusted spread
    apply_costs: bool = True
    liquidity_filter: bool = True
    # strategy parameters (fixed up front, not tuned on results)
    window: int = 60
    entry_z: float = 2.0
    exit_z: float = 0.5
    max_hold: int = 20
    min_volume: float = 50        # lots traded on the signal day, both legs
    costs: CostModel = field(default_factory=CostModel)
    # "z": thresholds are z-scores of the spread; "level": thresholds are the spread itself in bps
    # (e.g. a tip like "buy when it is 1% cheaper" is a level rule at 100 bps)
    threshold_mode: str = "z"
    sides: str = "both"           # "both", "long_a" (buy A when cheap) or "short_a" (sell A when rich)


LADDER = [
    ("Naive", dict(gram_matched=False, next_day_fill=False, rolling_stats=False,
                   true_contracts=False, apply_costs=False, liquidity_filter=False)),
    ("+ gram-matched sizing", dict(gram_matched=True)),
    ("+ fill next day", dict(next_day_fill=True)),
    ("+ past-only z-score", dict(rolling_stats=True)),
    ("+ real contracts & carry", dict(true_contracts=True)),
    ("+ costs", dict(apply_costs=True)),
    ("+ liquidity filter (honest)", dict(liquidity_filter=True)),
]


def ladder_configs(base: BacktestConfig | None = None) -> list[tuple[str, BacktestConfig]]:
    base = base or BacktestConfig()
    cfg = replace(base, **LADDER[0][1])
    out = [(LADDER[0][0], cfg)]
    for name, change in LADDER[1:]:
        cfg = replace(cfg, **change)
        out.append((name, cfg))
    return out


@dataclass
class BacktestResult:
    daily: pd.DataFrame          # gross, cost, net, position per day
    trades: pd.DataFrame
    metrics: dict
    signal: pd.DataFrame         # spread and z used


def _signal(pf: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    if cfg.true_contracts:
        x = pf["spread"].copy()
        valid = pf["traded_a"] & pf["traded_b"]
        if cfg.liquidity_filter:
            valid &= (pf["volume_a"] >= cfg.min_volume) & (pf["volume_b"] >= cfg.min_volume)
        x[~valid] = np.nan
    else:
        x = pf["spread_naive"].copy()
    if cfg.threshold_mode == "level":
        z = x  # rule thresholds are compared with the spread itself, in bps
    else:
        z = zscore(x, cfg.window, lookahead=not cfg.rolling_stats)
    return pd.DataFrame({"spread": x, "z": z})


def _targets(z: pd.Series, cfg: BacktestConfig) -> np.ndarray:
    """Desired position each day: +1 long A/short B, -1 short A/long B, 0 flat."""
    tgt = np.zeros(len(z), dtype=int)
    pos, held = 0, 0
    for i, v in enumerate(z.to_numpy()):
        if not np.isnan(v):
            if pos == 0:
                if v > cfg.entry_z and cfg.sides != "long_a":
                    pos, held = -1, 0
                elif v < -cfg.entry_z and cfg.sides != "short_a":
                    pos, held = 1, 0
            elif -pos * v < cfg.exit_z or held >= cfg.max_hold:
                pos = 0
        if pos != 0:
            held += 1
        tgt[i] = pos
    return tgt


def run_pair(pf: pd.DataFrame, cfg: BacktestConfig, prices: dict | None = None) -> BacktestResult:
    """Backtest one pair. `prices` maps (contract, date) -> quoted close for all contracts."""
    a, b = pf.attrs["a"], pf.attrs["b"]
    spec_a, spec_b = SPECS[a], SPECS[b]
    costs = cfg.costs if cfg.apply_costs else CostModel.zero()
    if cfg.gram_matched:
        lots_a, lots_b = LEG_GRAMS / spec_a.lot_grams, LEG_GRAMS / spec_b.lot_grams
    else:
        lots_a = lots_b = 1.0

    sig = _signal(pf, cfg)
    tgt = _targets(sig["z"], cfg)
    if cfg.next_day_fill:
        tgt = np.concatenate([[0], tgt[:-1]])

    dates = pf.index
    # Price lookups. Honest mode marks the exact contract held; naive mode marks the
    # stitched front-month series, so expiry jumps leak into P&L.
    if cfg.true_contracts:
        px = prices if prices is not None else _contract_prices(pf)
        act_a, act_b = pf["contract_a"].to_numpy(), pf["contract_b"].to_numpy()
    else:
        fa, fb = pf["close_fa"].to_numpy(), pf["close_fb"].to_numpy()

    gross = np.zeros(len(pf)); cost = np.zeros(len(pf)); pos_arr = np.zeros(len(pf))
    trades = []
    pos, ca, cb, entry = 0, None, None, None

    last_px = {}

    def price(i, leg):
        if not cfg.true_contracts:
            return fa[i] if leg == "a" else fb[i]
        c = ca if leg == "a" else cb
        p = px.get((c, dates[i]))
        if p is None or np.isnan(p):
            return last_px.get(c, np.nan)  # contract missing from that day's file
        last_px[c] = p
        return p

    def fill_cost(i, sign_a):
        """Cost of trading `sign_a` on A (and the opposite on B) at day i."""
        return (costs.leg_cost(spec_a, price(i, "a"), lots_a, sign_a)
                + costs.leg_cost(spec_b, price(i, "b"), lots_b, -sign_a))

    def close(i, reason):
        nonlocal pos, entry
        c = fill_cost(i, -pos)
        cost[i] += c
        entry["cost"] += c
        entry.update(exit_date=dates[i], exit_z=sig["z"].iloc[i], reason=reason)
        entry["net"] = entry["gross"] - entry["cost"]
        trades.append(entry)
        pos, entry = 0, None

    def open_(i, side):
        nonlocal pos, ca, cb, entry
        pos = side
        if cfg.true_contracts:
            ca, cb = act_a[i], act_b[i]
        c = fill_cost(i, side)
        cost[i] += c
        entry = dict(entry_date=dates[i], side=side, entry_z=sig["z"].iloc[i],
                     leg_a=ca if cfg.true_contracts else f"{a} (stitched)",
                     leg_b=cb if cfg.true_contracts else f"{b} (stitched)",
                     gross=0.0, cost=c)

    for i in range(len(pf)):
        # 1. mark yesterday's position to today's prices
        if pos != 0 and i > 0:
            pa0, pa1 = price(i - 1, "a"), price(i, "a")
            pb0, pb1 = price(i - 1, "b"), price(i, "b")
            g = pos * ((pa1 - pa0) * lots_a * spec_a.rupees_per_point
                       - (pb1 - pb0) * lots_b * spec_b.rupees_per_point)
            if not np.isnan(g):
                gross[i] += g
                entry["gross"] += g
        # 2. roll a held contract that has entered its expiry window
        if pos != 0 and cfg.true_contracts and (ca != act_a[i] or cb != act_b[i]):
            side = pos
            close(i, "roll")
            if tgt[i] == side:
                open_(i, side)
        # 3. trade towards today's target
        if tgt[i] != pos:
            if pos != 0:
                close(i, "signal")
            if tgt[i] != 0:
                open_(i, int(tgt[i]))
        pos_arr[i] = pos
    if pos != 0:
        close(len(pf) - 1, "end of data")

    daily = pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost,
                          "position": pos_arr}, index=dates)
    trades = pd.DataFrame(trades)
    return BacktestResult(daily, trades, _metrics(daily, trades, pf, lots_a, spec_a), sig)


def price_lookup(df: pd.DataFrame) -> dict:
    """(contract, date) -> quoted close for every contract in the normalised panel."""
    return dict(zip(zip(df["contract"], df["date"]), df["close"]))


def _contract_prices(pf: pd.DataFrame) -> dict:
    """Fallback lookup from a pair frame's active contracts only."""
    out = {}
    for leg in ("a", "b"):
        for d, c, p in zip(pf.index, pf[f"contract_{leg}"], pf[f"close_{leg}"]):
            out[(c, d)] = p
    return out


def _metrics(daily, trades, pf, lots_a, spec_a) -> dict:
    net = daily["net"]
    years = max((daily.index[-1] - daily.index[0]).days / 365.25, 1e-9)
    notional = (pf["close_a"] * lots_a * spec_a.rupees_per_point).mean()
    cum = net.cumsum()
    dd = (cum - cum.cummax()).min()
    sharpe = net.mean() / net.std() * np.sqrt(252) if net.std() > 0 else 0.0
    n = len(trades)
    return {
        "net_pnl": float(net.sum()),
        "gross_pnl": float(daily["gross"].sum()),
        "costs": float(daily["cost"].sum()),
        "trades": n,
        "win_rate": float((trades["net"] > 0).mean()) if n else 0.0,
        "avg_net_per_trade": float(trades["net"].mean()) if n else 0.0,
        "sharpe": float(sharpe),
        "max_drawdown": float(dd),
        "ann_return_pct": float(net.sum() / notional / years * 100) if notional else 0.0,
        "time_in_market": float((daily["position"] != 0).mean()),
        "notional": float(notional),
    }


def run_portfolio(pairs: dict, cfg: BacktestConfig, prices: dict | None = None
                  ) -> tuple[pd.DataFrame, dict, dict]:
    """Run every pair; return combined daily P&L, per-pair results and totals."""
    results = {k: run_pair(pf, cfg, prices) for k, pf in pairs.items()}
    daily = pd.concat({f"{a}/{b}": r.daily["net"] for (a, b), r in results.items()},
                      axis=1).fillna(0.0)
    daily["total"] = daily.sum(axis=1)
    tot = daily["total"]
    totals = {
        "net_pnl": float(tot.sum()),
        "gross_pnl": sum(r.metrics["gross_pnl"] for r in results.values()),
        "costs": sum(r.metrics["costs"] for r in results.values()),
        "trades": sum(r.metrics["trades"] for r in results.values()),
        "sharpe": float(tot.mean() / tot.std() * np.sqrt(252)) if tot.std() > 0 else 0.0,
        "max_drawdown": float((tot.cumsum() - tot.cumsum().cummax()).min()),
    }
    return daily, results, totals


def attribution(daily_net: pd.Series, gold_px10: pd.Series, grams: float = LEG_GRAMS) -> dict:
    """How much of the strategy's daily P&L is just gold moving.

    Regress daily P&L on the rupee change of holding `grams` of gold outright. Plain NumPy OLS
    with Newey-West (HAC, 5 lags) standard errors, so it needs no compiled statsmodels extension.
    """
    gold_rs = gold_px10.diff() * grams / 10.0
    j = pd.concat([daily_net, gold_rs], axis=1, keys=["pnl", "gold"]).dropna()
    j = j[j["pnl"] != 0]
    if len(j) < 20:
        return {"beta_grams": 0.0, "r2": 0.0, "gold_explained": 0.0, "alpha_per_day": 0.0, "n": len(j)}
    y = j["pnl"].to_numpy(float)
    X = np.column_stack([np.ones(len(j)), j["gold"].to_numpy(float)])
    xtx_inv = np.linalg.pinv(X.T @ X)
    coef = xtx_inv @ X.T @ y
    resid = y - X @ coef
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid ** 2).sum() / ss_tot if ss_tot > 0 else 0.0
    u = X * resid[:, None]
    S = u.T @ u
    lags = 5
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        g = u[lag:].T @ u[:-lag]
        S += w * (g + g.T)
    n, k = X.shape
    cov = xtx_inv @ S @ xtx_inv * n / (n - k)
    se_alpha = float(np.sqrt(max(cov[0, 0], 0.0)))
    beta = float(coef[1])
    return {"beta_grams": beta * grams, "r2": float(r2),
            "gold_explained": float(beta * j["gold"].sum()),
            "alpha_per_day": float(coef[0]),
            "alpha_t": float(coef[0] / se_alpha) if se_alpha > 0 else 0.0, "n": int(n)}
