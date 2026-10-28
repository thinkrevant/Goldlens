"""Per-visitor settings and cached calculations for the website."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from functools import lru_cache
from urllib.parse import quote, unquote

import pandas as pd

from ..backtest import BacktestConfig, ladder_configs, run_portfolio
from ..config import SYMBOLS, CostModel
from ..normalise import active_contracts
from ..pipeline import build_workspace
from ..signals import alerts as compute_alerts, fact_sheet

COOKIE = "goldlens"


@dataclass(frozen=True)
class Params:
    window: int = 60
    entry_z: float = 2.0
    exit_z: float = 0.5
    max_hold: int = 20
    min_volume: float = 50.0
    roll_bdays: int = 5
    slippage: float = 2.0
    brokerage: float = 20.0
    fees_on: bool = True
    language: str = "English"

    LIMITS = {"window": (20, 120), "entry_z": (1.5, 3.5), "exit_z": (0.0, 1.5), "max_hold": (5, 60),
              "min_volume": (0, 500), "roll_bdays": (2, 10), "slippage": (0.0, 6.0), "brokerage": (0, 100)}

    def cfg(self) -> BacktestConfig:
        costs = CostModel(brokerage_per_order=float(self.brokerage), slippage_ticks=float(self.slippage))
        if not self.fees_on:
            costs = replace(costs, exchange_rate=0, sebi_rate=0, ctt_rate=0, stamp_rate=0, gst_rate=0)
        return BacktestConfig(window=int(self.window), entry_z=float(self.entry_z), exit_z=float(self.exit_z),
                              max_hold=int(self.max_hold), min_volume=float(self.min_volume), costs=costs)

    @classmethod
    def parse(cls, raw: dict) -> "Params":
        """Build from untrusted input (cookie or form), clamping every number to its allowed range."""
        out = {}
        for f in fields(cls):
            if f.name not in raw:
                continue
            v = raw[f.name]
            try:
                if f.type in ("int", int):
                    v = int(float(v))
                elif f.type in ("float", float):
                    v = float(v)
                elif f.type in ("bool", bool):
                    v = v in (True, "true", "on", "1", 1)
                else:
                    v = "Hindi" if str(v) == "Hindi" else "English"
            except (TypeError, ValueError):
                continue
            if f.name in cls.LIMITS:
                lo, hi = cls.LIMITS[f.name]
                v = type(v)(min(max(v, lo), hi))
            out[f.name] = v
        return cls(**out)

    @classmethod
    def from_cookie(cls, value: str | None) -> "Params":
        if not value:
            return cls()
        try:
            return cls.parse(json.loads(unquote(value)))
        except (ValueError, TypeError):
            return cls()

    def to_cookie(self) -> str:
        return quote(json.dumps(asdict(self)))


@lru_cache(maxsize=4)
def workspace(roll: int):
    return build_workspace(roll)


@lru_cache(maxsize=16)
def ladder(p: Params) -> list:
    ws = workspace(p.roll_bdays)
    out = []
    for name, cfg in ladder_configs(p.cfg()):
        daily, _, tot = run_portfolio(ws.pairs, cfg, ws.prices)
        out.append((name, daily["total"], tot))
    return out


@lru_cache(maxsize=64)
def custom(p: Params, flags: tuple = ()):
    ws = workspace(p.roll_bdays)
    return run_portfolio(ws.pairs, replace(p.cfg(), **dict(flags)), ws.prices)


@lru_cache(maxsize=16)
def today(p: Params) -> tuple[list[dict], dict, dict]:
    """(alert rows, honest totals, AI fact sheet) exactly as the dashboard shows them."""
    ws = workspace(p.roll_bdays)
    lad = ladder(p)
    honest = custom(p)[2]
    rows = compute_alerts(ws.pairs, p.cfg())
    return rows, honest, fact_sheet(ws.curves, rows, honest, [(n, t) for n, _, t in lad])


@lru_cache(maxsize=4)
def watch(roll: int) -> list[dict]:
    """Active contract per symbol on the last day: price, day change, premium, 60-day sparkline."""
    ws = workspace(roll)
    last_day = ws.df["date"].max()
    act = active_contracts(ws.df, roll).xs(last_day, level="date")
    curve = ws.curves.iloc[-1]
    rows = []
    for sym in SYMBOLS:
        if sym not in act.index:
            continue
        r = act.loc[sym]
        hist = ws.front.xs(sym, level="symbol")["px10"].tail(60)
        rows.append({"symbol": sym, "contract": r["contract"].split(" ", 1)[1], "quoted": r["close"], "px10": r["px10"],
                     "chg": (r["close"] / r["prev_close"] - 1) * 100 if r["prev_close"] else 0.0,
                     "premium": None if sym == "GOLDM" else curve.get(f"premium_{sym}"),
                     "volume": r["volume"], "oi": r["oi"], "spark": hist.tolist()})
    return rows


def clear():
    """Forget every cached result (after new MCX data arrives)."""
    for fn in (workspace, ladder, custom, today, watch):
        fn.cache_clear()


def last_day(p: Params) -> pd.Timestamp:
    return workspace(p.roll_bdays).df["date"].max()
