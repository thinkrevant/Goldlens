"""Fair curve, carry, cross-contract premiums and pair spreads.

Each day we fit one log-linear curve across all traded contracts:

    ln px10 = ln S + r * tau + premium[symbol]        (GOLDM premium fixed at 0)

r is the market-implied annual carry, and premium[symbol] is how rich (+) or cheap (-)
a contract trades against GOLDM after units, purity and time to expiry are removed.
GOLDM is the anchor because it is the most liquid of the four and listed throughout
(GOLDTEN only appears later in the history).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PAIRS, SYMBOLS
from .normalise import DEFAULT_ROLL_BDAYS, active_contracts, front_contracts

REF = "GOLDM"
OTHERS = [s for s in SYMBOLS if s != REF]


def fit_curves(df: pd.DataFrame, max_tau: float = 0.6, min_volume: float = 1) -> pd.DataFrame:
    """One weighted regression per day. Returns ln_s, carry and premium_<SYM> in bps."""
    use = df[(df["volume"] >= min_volume) & (df["tau"] <= max_tau)]
    out = []
    for day, g in use.groupby("date"):
        if (g["symbol"] == REF).sum() < 1 or len(g) < 4:
            continue
        X = np.column_stack([np.ones(len(g)), g["tau"].to_numpy()] +
                            [(g["symbol"] == s).to_numpy(float) for s in OTHERS])
        y = np.log(g["px10"].to_numpy())
        w = np.sqrt(g["volume"].to_numpy())
        present = X.any(axis=0)  # drop dummies for symbols missing that day
        Xp = X[:, present]
        coef_p, *_ = np.linalg.lstsq(Xp * w[:, None], y * w, rcond=None)
        coef = np.full(X.shape[1], np.nan)
        coef[present] = coef_p
        resid = y - Xp @ coef_p
        row = {"date": day, "ln_s": coef[0], "carry": coef[1], "n": len(g),
               "fit_rmse_bps": float(np.sqrt(np.average(resid ** 2, weights=w)) * 1e4)}
        for i, s in enumerate(OTHERS):
            row[f"premium_{s}"] = coef[2 + i] * 1e4
        out.append(row)
    curves = pd.DataFrame(out).set_index("date")
    curves["spot_implied"] = np.exp(curves["ln_s"])
    return curves


def pair_frame(df: pd.DataFrame, curves: pd.DataFrame, a: str, b: str,
               roll_bdays: int = DEFAULT_ROLL_BDAYS) -> pd.DataFrame:
    """Daily table for one pair with both the honest and the naive spread."""
    act = active_contracts(df, roll_bdays)
    fr = front_contracts(df)
    cols = ["contract", "close", "px10", "tau", "volume", "oi", "traded"]

    def leg(table, sym, tag):
        t = table.xs(sym, level="symbol")[cols]
        return t.add_suffix(f"_{tag}")

    pf = pd.concat([leg(act, a, "a"), leg(act, b, "b"),
                    fr.xs(a, level="symbol")[["contract", "close", "px10"]].add_suffix("_fa"),
                    fr.xs(b, level="symbol")[["contract", "close", "px10"]].add_suffix("_fb")],
                   axis=1, join="inner")
    pf = pf.join(curves[["carry"]], how="left")
    pf["carry"] = pf["carry"].ffill()
    # Honest: own contracts, carry removed so different expiries compare fairly.
    pf["spread"] = 1e4 * (np.log(pf["px10_a"] / pf["px10_b"])
                          - pf["carry"] * (pf["tau_a"] - pf["tau_b"]))
    # Naive: stitched front months, no carry adjustment.
    pf["spread_naive"] = 1e4 * np.log(pf["px10_fa"] / pf["px10_fb"])
    pf.attrs.update(a=a, b=b)
    return pf.sort_index()


def zscore(x: pd.Series, window: int = 60, lookahead: bool = False) -> pd.Series:
    """Rolling z-score from past data only (or full-sample when lookahead=True)."""
    if lookahead:
        return (x - x.mean()) / x.std()
    past = x.shift(1).rolling(window, min_periods=window // 2)
    return (x - past.mean()) / past.std()


def rolldown_decomposition(curves: pd.DataFrame, tau0: float, start, end) -> dict:
    """Split the move of a contract with tau0 years left (at start) into parts.

    ln F = ln S + r * tau. Over the period:
      level shift  = change in ln S
      carry shift  = change in r, times the remaining tau
      roll-down    = r times the change in tau (time passing, always pulls F towards S)
    """
    c = curves.loc[start:end]
    if len(c) < 2:
        return {}
    days = (c.index[-1] - c.index[0]).days
    tau1 = max(tau0 - days / 365.0, 0.0)
    f0 = c["ln_s"].iloc[0] + c["carry"].iloc[0] * tau0
    f1 = c["ln_s"].iloc[-1] + c["carry"].iloc[-1] * tau1
    level = c["ln_s"].iloc[-1] - c["ln_s"].iloc[0]
    carry_shift = (c["carry"].iloc[-1] - c["carry"].iloc[0]) * tau1
    rolldown = c["carry"].iloc[0] * (tau1 - tau0)
    return {"total_bps": (f1 - f0) * 1e4, "level_bps": level * 1e4,
            "carry_shift_bps": carry_shift * 1e4, "rolldown_bps": rolldown * 1e4,
            "days": days}


def all_pairs(df, curves, roll_bdays: int = DEFAULT_ROLL_BDAYS,
              min_days: int = 40) -> dict[tuple, pd.DataFrame]:
    """Pair frames for every configured pair with enough shared history."""
    listed = set(df["symbol"])
    out = {}
    for a, b in PAIRS:
        if a in listed and b in listed:
            pf = pair_frame(df, curves, a, b, roll_bdays)
            if len(pf) >= min_days:
                out[(a, b)] = pf
    return out
