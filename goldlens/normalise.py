"""Put every contract on one scale and track each one by its own expiry.

px10 = quoted close x (10 / quote grams) x (999 / purity), i.e. Rs per 10 g of 999 gold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SPECS

# MCX moves gold contracts into the tender/delivery period in the last few
# trading days. We roll out this many business days before expiry.
DEFAULT_ROLL_BDAYS = 5


def normalise(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["to_base"] = df["symbol"].map({s: spec.to_base for s, spec in SPECS.items()})
    df["px10"] = df["close"] * df["to_base"]
    df["dte"] = (df["expiry"] - df["date"]).dt.days
    df["tau"] = df["dte"] / 365.0
    df["bdte"] = np.busday_count(df["date"].values.astype("datetime64[D]"),
                                 df["expiry"].values.astype("datetime64[D]"))
    df["contract"] = df["symbol"] + " " + df["expiry"].dt.strftime("%d%b%y").str.upper()
    return df


def front_contracts(df: pd.DataFrame) -> pd.DataFrame:
    """Nearest expiry per symbol per day: what a stitched continuous series uses."""
    idx = df.groupby(["date", "symbol"])["expiry"].idxmin()
    return df.loc[idx].set_index(["date", "symbol"]).sort_index()


def active_contracts(df: pd.DataFrame, roll_bdays: int = DEFAULT_ROLL_BDAYS) -> pd.DataFrame:
    """Nearest expiry that is still outside the roll window: the one we would hold."""
    live = df[df["bdte"] > roll_bdays]
    idx = live.groupby(["date", "symbol"])["expiry"].idxmin()
    return live.loc[idx].set_index(["date", "symbol"]).sort_index()


def contract_calendar(df: pd.DataFrame, roll_bdays: int = DEFAULT_ROLL_BDAYS) -> pd.DataFrame:
    """Listing, roll-out and expiry dates for every contract seen in the data."""
    g = df.groupby(["symbol", "expiry", "contract"])
    cal = g.agg(first_seen=("date", "min"), last_seen=("date", "max"),
                peak_oi=("oi", "max"), total_volume=("volume", "sum")).reset_index()
    exp = cal["expiry"].values.astype("datetime64[D]")
    cal["roll_out"] = pd.to_datetime(np.busday_offset(exp, -roll_bdays, roll="backward"))
    return cal.sort_values(["symbol", "expiry"]).reset_index(drop=True)
