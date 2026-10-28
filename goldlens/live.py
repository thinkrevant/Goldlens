"""Live MCX gold quotes from the Upstox API, with automatic fallback to daily data.

Auth uses an Upstox Analytics Token: free, read-only, valid for one year, generated in
the Upstox Developer Apps page (Analytics tab). It goes in .env as UPSTOX_ANALYTICS_TOKEN.

Live spreads are scored against the same past-only statistics the daily scanner uses,
and the cost check uses the live order book: crossing the bid-ask spread is the real
slippage, so the live alert is stricter than the daily one when books are thin.
"""
from __future__ import annotations

import gzip
import json
import os
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests

from .analytics import fit_curves
from .backtest import BacktestConfig, _signal
from .config import DATA_DIR, LEG_GRAMS, SPECS, SYMBOLS, CostModel
from .normalise import DEFAULT_ROLL_BDAYS, active_contracts, normalise

INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json.gz"
QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"
INSTRUMENTS_CACHE = DATA_DIR / "upstox_mcx_gold.json"
IST = "Asia/Kolkata"
STALE_AFTER = pd.Timedelta(minutes=5)


class LiveDataError(RuntimeError):
    """Anything that stops live quotes: missing token, auth, network, bad payload."""


def get_token() -> str | None:
    return (os.environ.get("UPSTOX_ANALYTICS_TOKEN") or os.environ.get("UPSTOX_ACCESS_TOKEN") or "").strip() or None


def refresh_seconds() -> int:
    try:
        return max(5, int(os.environ.get("UPSTOX_REFRESH_SECONDS", "10")))
    except ValueError:
        return 10


def _ist_date(ms) -> pd.Timestamp:
    return pd.to_datetime(int(ms), unit="ms", utc=True).tz_convert(IST).normalize().tz_localize(None)


def parse_instruments(records: list[dict]) -> pd.DataFrame:
    rows = [{
        "symbol": r["underlying_symbol"], "instrument_key": r["instrument_key"],
        "trading_symbol": r.get("trading_symbol"), "expiry": _ist_date(r["expiry"]),
        "lot_size": r.get("lot_size"),
    } for r in records
        if r.get("instrument_type") == "FUT" and r.get("segment") == "MCX_FO"
        and r.get("underlying_symbol") in SYMBOLS]
    return pd.DataFrame(rows).sort_values(["symbol", "expiry"]).reset_index(drop=True)


def load_instruments(max_age_hours: float = 12) -> pd.DataFrame:
    """MCX gold futures from Upstox's public instrument file, cached on disk."""
    fresh = INSTRUMENTS_CACHE.exists() and (time.time() - INSTRUMENTS_CACHE.stat().st_mtime) < max_age_hours * 3600
    if not fresh:
        try:
            r = requests.get(INSTRUMENTS_URL, timeout=30)
            r.raise_for_status()
            records = json.loads(gzip.decompress(r.content))
            gold = [x for x in records if x.get("underlying_symbol") in SYMBOLS and x.get("instrument_type") == "FUT"]
            INSTRUMENTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
            INSTRUMENTS_CACHE.write_text(json.dumps(gold))
        except (requests.RequestException, OSError, ValueError) as e:
            if not INSTRUMENTS_CACHE.exists():
                raise LiveDataError(f"could not download the Upstox instrument list ({type(e).__name__})") from e
    return parse_instruments(json.loads(INSTRUMENTS_CACHE.read_text()))


def fetch_quotes(keys: list[str], token: str, timeout: float = 10) -> pd.DataFrame:
    """Full market quotes for up to 500 instrument keys."""
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    try:
        r = requests.get(QUOTE_URL, params={"instrument_key": ",".join(keys)}, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise LiveDataError(f"network error reaching Upstox ({type(e).__name__})") from e
    if r.status_code == 401:
        raise LiveDataError("Upstox rejected the token (401). Generate a new Analytics Token and update .env")
    if r.status_code == 429:
        raise LiveDataError("Upstox rate limit hit (429). Increase UPSTOX_REFRESH_SECONDS")
    if r.status_code != 200:
        raise LiveDataError(f"Upstox returned HTTP {r.status_code}")
    try:
        payload = r.json()
    except ValueError as e:
        raise LiveDataError("Upstox returned a non-JSON response") from e
    if payload.get("status") != "success":
        raise LiveDataError(f"Upstox error: {payload.get('errors') or payload}")
    return parse_quotes(payload.get("data") or {})


def parse_quotes(data: dict) -> pd.DataFrame:
    rows = []
    for q in data.values():
        depth = q.get("depth") or {}
        bids = [d for d in depth.get("buy") or [] if d.get("price")]
        asks = [d for d in depth.get("sell") or [] if d.get("price")]
        ltt = q.get("last_trade_time")
        rows.append({
            "instrument_key": q.get("instrument_token"),
            "last_price": float(q.get("last_price") or np.nan),
            "bid": float(bids[0]["price"]) if bids else np.nan,
            "ask": float(asks[0]["price"]) if asks else np.nan,
            "volume": float(q.get("volume") or 0),
            "oi": float(q.get("oi") or 0),
            "last_trade_time": (pd.to_datetime(int(ltt), unit="ms", utc=True).tz_convert(IST)
                                if ltt not in (None, "", "0") else pd.NaT),
        })
    return pd.DataFrame(rows)


@dataclass
class LiveSnapshot:
    ok: bool
    source: str                       # "upstox" or "daily"
    message: str
    fetched_at: pd.Timestamp | None = None
    last_trade: pd.Timestamp | None = None
    stale: bool = False
    quotes: pd.DataFrame = field(default_factory=pd.DataFrame)   # normalised panel-like rows
    carry: float | None = None


def snapshot(roll_bdays: int = DEFAULT_ROLL_BDAYS, token: str | None = None) -> LiveSnapshot:
    """Fetch live quotes for every listed gold future. Never raises: failures come back as ok=False."""
    token = token or get_token()
    if not token:
        return LiveSnapshot(False, "daily", "No UPSTOX_ANALYTICS_TOKEN in .env, so showing the daily scanner.")
    try:
        inst = load_instruments()
        q = fetch_quotes(inst["instrument_key"].tolist(), token)
    except LiveDataError as e:
        return LiveSnapshot(False, "daily", f"Live data unavailable: {e}. Showing the daily scanner.")
    if q.empty:
        return LiveSnapshot(False, "daily", "Upstox returned no gold quotes. Showing the daily scanner.")

    now = pd.Timestamp.now(tz=IST)
    df = inst.merge(q, on="instrument_key", how="inner")
    mid = (df["bid"] + df["ask"]) / 2
    use_mid = df["bid"].gt(0) & df["ask"].gt(0) & df["ask"].ge(df["bid"])
    df["close"] = np.where(use_mid, mid, df["last_price"])
    df["date"] = now.normalize().tz_localize(None)
    df["traded"] = df["volume"] > 0
    df = df[df["expiry"] >= df["date"]].copy()
    norm = normalise(df[["date", "symbol", "expiry", "close", "volume", "oi", "traded",
                         "bid", "ask", "last_price", "last_trade_time", "instrument_key"]])
    last_trade = norm["last_trade_time"].max()
    stale = bool(pd.isna(last_trade) or now - last_trade > STALE_AFTER)
    carry = None
    try:
        cur = fit_curves(norm)
        if len(cur):
            carry = float(cur["carry"].iloc[-1])
    except (ValueError, np.linalg.LinAlgError):
        pass
    msg = (f"Live from Upstox · last trade {last_trade:%d %b %H:%M:%S} IST"
           + (" · market looks closed, these are the last traded prices" if stale else ""))
    return LiveSnapshot(True, "upstox", msg, now, last_trade, stale, norm, carry)


def live_alerts(snap: LiveSnapshot, pairs: dict, curves: pd.DataFrame, cfg: BacktestConfig,
                roll_bdays: int = DEFAULT_ROLL_BDAYS, cost_margin: float = 1.5) -> list[dict]:
    """Score each pair's live spread against its past-only daily statistics."""
    act = active_contracts(snap.quotes, roll_bdays)
    carry = snap.carry if snap.carry is not None else float(curves["carry"].dropna().iloc[-1])
    fee_only = CostModel(**{**cfg.costs.__dict__, "slippage_ticks": 0.0})
    out = []
    for (a, b), pf in pairs.items():
        try:
            la = act.xs(a, level="symbol").iloc[-1]
            lb = act.xs(b, level="symbol").iloc[-1]
        except KeyError:
            continue
        hist = _signal(pf, cfg)["spread"].dropna().tail(cfg.window)
        mean, std = hist.mean(), hist.std()
        spread = 1e4 * (np.log(la["px10"] / lb["px10"]) - carry * (la["tau"] - lb["tau"]))
        z = (spread - mean) / std if std and std > 0 else np.nan
        sa, sb = SPECS[a], SPECS[b]
        lots_a, lots_b = LEG_GRAMS / sa.lot_grams, LEG_GRAMS / sb.lot_grams
        # Real slippage: buy at the ask and sell at the bid, i.e. one full bid-ask spread per leg per round trip.
        book = 0.0
        book_ok = True
        for leg, lots, spec in ((la, lots_a, sa), (lb, lots_b, sb)):
            width = leg["ask"] - leg["bid"]
            if not (leg["bid"] > 0 and leg["ask"] > 0 and width >= 0):
                book_ok = False
                width = 2 * cfg.costs.slippage_ticks * spec.tick  # no book: fall back to the tick assumption
            book += width * lots * spec.rupees_per_point
        fees = sum(fee_only.leg_cost(sa, la["close"], lots_a, s) + fee_only.leg_cost(sb, lb["close"], lots_b, -s)
                   for s in (1, -1))
        cost = book + fees
        notional = la["px10"] * LEG_GRAMS / 10.0
        edge = abs(spread - mean) / 1e4 * notional if pd.notna(mean) else np.nan
        liquid = bool(la["volume"] >= cfg.min_volume and lb["volume"] >= cfg.min_volume)
        flagged = pd.notna(z) and abs(z) >= cfg.entry_z
        passes = bool(flagged and liquid and book_ok and not snap.stale and edge >= cost_margin * cost)
        if snap.stale:
            status = "Market closed"
        elif not liquid:
            status = "Illiquid: no signal"
        elif passes:
            status = "ALERT"
        elif flagged:
            status = "Flagged, below cost"
        else:
            status = "Normal"
        out.append({
            "pair": f"{a}/{b}", "a": a, "b": b, "leg_a": la["contract"], "leg_b": lb["contract"],
            "spread_bps": float(spread), "mean_bps": float(mean), "std_bps": float(std), "z": float(z),
            "rich": (a if z > 0 else b) if flagged else None,
            "edge_rs": float(edge), "round_trip_cost_rs": float(cost), "book_cost_rs": float(book),
            "bid_a": la["bid"], "ask_a": la["ask"], "bid_b": lb["bid"], "ask_b": lb["ask"],
            "volume_a": la["volume"], "volume_b": lb["volume"], "liquid": liquid,
            "passes_cost_check": passes, "status": status,
        })
    order = {"ALERT": 0, "Flagged, below cost": 1, "Normal": 2, "Illiquid: no signal": 3, "Market closed": 4}
    return sorted(out, key=lambda r: (order[r["status"]], -abs(r["z"]) if r["z"] == r["z"] else 0))
