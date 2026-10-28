"""Load the cached panel and compute everything the dashboard needs."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from .analytics import all_pairs, fit_curves
from .backtest import price_lookup
from .config import PANEL_PATH, RAW_DIR
from .ingest import build_panel
from .normalise import DEFAULT_ROLL_BDAYS, contract_calendar, front_contracts, normalise


@dataclass
class Workspace:
    df: pd.DataFrame
    curves: pd.DataFrame
    pairs: dict
    prices: dict
    calendar: pd.DataFrame
    front: pd.DataFrame
    roll_bdays: int


def load_panel() -> pd.DataFrame:
    if PANEL_PATH.exists():
        return pd.read_parquet(PANEL_PATH)
    return build_panel()


def build_workspace(roll_bdays: int = DEFAULT_ROLL_BDAYS) -> Workspace:
    df = normalise(load_panel())
    curves = fit_curves(df)
    return Workspace(df=df, curves=curves, pairs=all_pairs(df, curves, roll_bdays),
                     prices=price_lookup(df), calendar=contract_calendar(df, roll_bdays),
                     front=front_contracts(df), roll_bdays=roll_bdays)


def daily_facts(ws: Workspace, cfg=None) -> tuple[list[dict], dict, dict]:
    """Today's alerts, the honest backtest totals and the AI fact sheet, as the dashboard computes them."""
    from .backtest import BacktestConfig, ladder_configs, run_portfolio
    from .signals import alerts, fact_sheet

    cfg = cfg or BacktestConfig()
    ladder = [(name, run_portfolio(ws.pairs, c, ws.prices)[2]) for name, c in ladder_configs(cfg)]
    honest = ladder[-1][1]
    rows = alerts(ws.pairs, cfg)
    return rows, honest, fact_sheet(ws.curves, rows, honest, ladder)


def data_quality(df: pd.DataFrame) -> dict:
    """Counts from the raw cache and the panel, for the data-quality tab."""
    status = Counter()
    for p in RAW_DIR.glob("*.json"):
        try:
            status[json.loads(p.read_text())["status"]] += 1
        except (OSError, ValueError, KeyError):
            status["unreadable"] += 1
    return {
        "days_requested": sum(status.values()),
        "trading_days": int(status.get("ok", 0)),
        "holidays": int(status.get("holiday", 0)),
        "rejected_date_mismatch": int(status.get("rejected", 0)),
        "rows": len(df),
        "contracts": int(df["contract"].nunique()),
        "stale_rows": int((~df["traded"]).sum()),
        "stale_share": float((~df["traded"]).mean()),
        "first_day": df["date"].min().date().isoformat(),
        "last_day": df["date"].max().date().isoformat(),
    }
