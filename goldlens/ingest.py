"""Download, validate and cache MCX daily Bhavcopy rows for gold futures.

MCX sits behind Akamai, which rejects plain Python HTTP clients, so we use
curl_cffi to present a normal Chrome TLS fingerprint. The endpoint is public.

Quirks handled here:
  * requests take DD/MM/YYYY, responses carry MM/DD/YYYY, expiries look like 04SEP2026
  * on holidays the API can return another day's file, so any row whose date
    differs from the requested date rejects the whole day
  * symbols come space-padded
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta

import pandas as pd

from .config import PANEL_PATH, RAW_DIR, SYMBOLS

BASE = "https://www.mcxindia.com/market-data/bhavcopy"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
    "Referer": BASE,
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Site": "same-origin",
}
GOLD_PREFIX = "GOLD"


class MCXClient:
    def __init__(self, pause: float = 0.35):
        from curl_cffi import requests  # imported lazily so the app runs without it

        self.session = requests.Session(impersonate="chrome")
        self.pause = pause
        self._warm = False

    def _warmup(self):
        if not self._warm:
            self.session.get(BASE, timeout=60)
            self._warm = True

    def fetch_day(self, day: date) -> list[dict] | None:
        """Raw FUTCOM rows for one day; None when MCX has no file for it."""
        self._warmup()
        params = {"InstrumentName": "FUTCOM", "fromDate": day.strftime("%d/%m/%Y")}
        for attempt in range(4):
            try:
                r = self.session.get(f"{BASE}/GetDateWiseBhavCopy", params=params,
                                     headers=HEADERS, timeout=60)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    payload = r.json()
                    time.sleep(self.pause)
                    return payload.get("Data") or None
            except Exception:
                pass
            # stale session or throttling: back off and re-warm
            time.sleep(2 * (attempt + 1))
            self._warm = False
            self._warmup()
        raise RuntimeError(f"MCX did not return JSON for {day}")


def validate_day(day: date, rows: list[dict] | None) -> tuple[str, list[dict]]:
    """Return (status, gold rows). status is 'ok', 'holiday' or 'rejected'."""
    if not rows:
        return "holiday", []
    want = day.strftime("%m/%d/%Y")
    if any(r.get("Date") != want for r in rows):
        return "rejected", []
    gold = [r for r in rows if (r.get("Symbol") or "").strip().startswith(GOLD_PREFIX)]
    return ("ok" if gold else "holiday"), gold


def raw_path(day: date):
    return RAW_DIR / f"{day.isoformat()}.json"


def download(start: date, end: date, pause: float = 0.35, verbose: bool = True) -> dict:
    """Fetch every weekday in [start, end] that is not cached yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    client = MCXClient(pause=pause)
    stats = {"ok": 0, "holiday": 0, "rejected": 0, "cached": 0}
    day = start
    while day <= end:
        if day.weekday() < 5:
            path = raw_path(day)
            if path.exists():
                stats["cached"] += 1
            else:
                status, gold = validate_day(day, client.fetch_day(day))
                path.write_text(json.dumps({"date": day.isoformat(), "status": status, "rows": gold}))
                stats[status] += 1
                if verbose:
                    print(f"{day} {status:8s} {len(gold):3d} gold rows", flush=True)
        day += timedelta(days=1)
    return stats


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def build_panel(save: bool = True) -> pd.DataFrame:
    """Combine cached days into one tidy table, one row per (date, symbol, expiry)."""
    records = []
    for path in sorted(RAW_DIR.glob("*.json")):
        blob = json.loads(path.read_text())
        if blob["status"] != "ok":
            continue
        for r in blob["rows"]:
            sym = r["Symbol"].strip()
            if sym not in SYMBOLS:
                continue
            records.append({
                "date": pd.Timestamp(blob["date"]),
                "symbol": sym,
                "expiry": pd.Timestamp(datetime.strptime(r["ExpiryDate"].strip(), "%d%b%Y")),
                "open": _num(r["Open"]), "high": _num(r["High"]), "low": _num(r["Low"]),
                "close": _num(r["Close"]), "prev_close": _num(r["PreviousClose"]),
                "volume": _num(r["Volume"]), "oi": _num(r["OpenInterest"]),
                "value_lakh": _num(r["Value"]),
            })
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df.sort_values(["date", "symbol", "expiry"]).drop_duplicates(["date", "symbol", "expiry"])
    # A zero-volume row only repeats the previous close: it is not a tradeable price.
    df["traded"] = df["volume"] > 0
    df = df[df["expiry"] >= df["date"]].reset_index(drop=True)
    if save:
        PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(PANEL_PATH, index=False)
    return df


def load_panel() -> pd.DataFrame:
    return pd.read_parquet(PANEL_PATH)


def main():
    ap = argparse.ArgumentParser(description="Download MCX gold futures Bhavcopy history")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--pause", type=float, default=0.35)
    args = ap.parse_args()
    stats = download(date.fromisoformat(args.start), date.fromisoformat(args.end), args.pause)
    df = build_panel()
    print("download:", stats)
    print(f"panel: {len(df)} rows, {df['date'].nunique()} trading days, "
          f"{df['date'].min():%Y-%m-%d} to {df['date'].max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
