"""GoldLens morning briefing on Telegram.

    python -m goldlens.notify --setup     # once: connect the bot in .env to your chat
    python -m goldlens.notify             # refresh MCX data and send today's morning message
    python -m goldlens.notify --test      # send a short test message

Each morning gets exactly one message: market snapshot, signals (alerts included), premiums,
upcoming expiries and roll dates, and a short AI take. It is sent once per settlement date.
`--alerts-only` sends any new alert on its own, for runs during the trading day.
Schedule it for the morning (e.g. 8:30 am IST, after MCX publishes the Bhavcopy).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

import pandas as pd

from .config import DATA_DIR, RAW_DIR, ROOT
from . import telegram

STATE_PATH = DATA_DIR / "telegram_state.json"
ENV_PATH = ROOT / ".env"
DAILY_SCRIPT = ROOT / "scripts" / "telegram_daily.cmd"


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)
    except ImportError:
        pass


def _state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {"daily": [], "alerts": []}


def _save_state(s: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    s["daily"], s["alerts"] = s["daily"][-60:], s["alerts"][-300:]
    STATE_PATH.write_text(json.dumps(s, indent=1))


def set_env_value(key: str, value: str, path=None):
    """Add or replace KEY=value in .env without touching other lines."""
    path = path or ENV_PATH
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{key}={value}"
    if re.search(rf"^{re.escape(key)}=.*$", text, flags=re.M):
        text = re.sub(rf"^{re.escape(key)}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    path.write_text(text, encoding="utf-8")


def refresh_data() -> str:
    """Download any trading days missing since the last cached file."""
    from .ingest import build_panel, download

    cached = sorted(p.stem for p in RAW_DIR.glob("*.json"))
    start = (date.fromisoformat(cached[-1]) + timedelta(days=1)) if cached else date(2023, 1, 1)
    today = date.today()
    if start > today:
        return "data already up to date"
    try:
        stats = download(start, today, verbose=False)
    except Exception as e:  # MCX unreachable: carry on with the cached data
        return f"refresh failed ({type(e).__name__}); using cached data"
    build_panel()
    return f"refreshed {start} to {today}: {stats.get('ok', 0)} new trading day(s)"


# ---------------------------------------------------------------- morning message
def morning_context(ws, rows: list[dict], today: date | None = None, horizon_days: int = 10) -> dict:
    """The day-specific facts the morning message needs beyond the fact sheet."""
    today = pd.Timestamp(today or date.today())
    spot = ws.curves["spot_implied"].dropna()
    spot_dd = float((spot.iloc[-1] / spot.iloc[-2] - 1) * 100) if len(spot) > 1 else None
    cal = ws.calendar
    soon = cal[(cal["expiry"] >= today) & (cal["expiry"] <= today + pd.Timedelta(days=horizon_days))]
    events = [{"expiry": exp, "symbols": sorted(g["symbol"]), "roll_out": g["roll_out"].min()}
              for exp, g in soon.groupby("expiry")]
    others = [a for a in rows if a["status"] != "ALERT" and a.get("z") == a.get("z") and a.get("z") is not None]
    nearest = max(others, key=lambda a: abs(a["z"]), default=None)
    return {"today": today, "spot_dd": spot_dd, "events": events, "nearest": nearest}


def build_morning(ws, rows, facts, lang: str = "English", use_ai: bool = True, today: date | None = None) -> tuple[str, str]:
    """(Telegram HTML message, who wrote the AI take)."""
    from . import ai

    if use_ai:
        take = ai.complete("morning", facts, lang)
        by = ai.last_used or "template"
    else:
        take, by = ai.cached("morning", facts, lang), ""
    if take and "Template brief" in take:
        take, by = None, "template"
    url = (os.environ.get("GOLDLENS_DASHBOARD_URL") or "").strip() or None
    return telegram.morning_message(facts, morning_context(ws, rows, today), take, rows, url), by


def send_morning(ws, rows, facts, lang: str = "English") -> str:
    """Send today's morning message now and record it, so the scheduled run won't repeat it."""
    msg, by = build_morning(ws, rows, facts, lang)
    telegram.send(msg)
    state = _state()
    if facts["as_of"] not in state["daily"]:
        state["daily"].append(facts["as_of"])
    state["alerts"] += [f"{facts['as_of']}|{a['pair']}" for a in rows if a["status"] == "ALERT"]
    _save_state(state)
    return f"Morning message sent (AI take by {by})."


def run(lang: str, force: bool = False, alerts_only: bool = False, refresh: bool = True) -> str:
    from .pipeline import build_workspace, daily_facts

    notes = [refresh_data()] if refresh else []
    ws = build_workspace()
    rows, honest, facts = daily_facts(ws)
    state = _state()
    sent = 0
    live = [a for a in rows if a["status"] == "ALERT"]
    if alerts_only:
        for a in live:
            key = f"{facts['as_of']}|{a['pair']}"
            if force or key not in state["alerts"]:
                sent += telegram.send(telegram.alert_message(a))
                state["alerts"].append(key)
                notes.append(f"alert sent: {a['pair']}")
    elif force or facts["as_of"] not in state["daily"]:
        msg, by = build_morning(ws, rows, facts, lang)
        sent += telegram.send(msg)
        state["daily"].append(facts["as_of"])
        state["alerts"] += [f"{facts['as_of']}|{a['pair']}" for a in live]  # already in the morning message
        notes.append(f"morning message for {facts['as_of']} sent (AI: {by})")
    else:
        notes.append(f"morning message for {facts['as_of']} already sent (use --force to resend)")
    if not live:
        notes.append("no alerts today (quiet by design)")
    _save_state(state)
    return "; ".join(notes) + f"; {sent} Telegram message(s)"


# ---------------------------------------------------------------- connecting
def connect(token: str) -> tuple[bool, str]:
    """Check the token, find the chat that pressed Start, save both to .env and say hello."""
    token = (token or "").strip()
    if not re.fullmatch(r"\d{5,}:[\w-]{20,}", token):
        return False, "That doesn't look like a bot token. It should look like 123456789:AAH… (copy it from @BotFather)."
    try:
        me = telegram.get_me(token)
        found = telegram.find_chat_id(token)
    except telegram.TelegramError as e:
        return False, str(e)
    handle = f"@{me.get('username', 'your bot')}"
    if not found:
        set_env_value("TELEGRAM_BOT_TOKEN", token)
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        return False, (f"Token works for {handle}. Now open t.me/{me.get('username', '')} in Telegram, press "
                       "Start, then click Connect again.")
    chat_id, name = found
    set_env_value("TELEGRAM_BOT_TOKEN", token)
    set_env_value("TELEGRAM_CHAT_ID", chat_id)
    os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = token, chat_id
    try:
        telegram.send("✅ <b>GoldLens is connected.</b>\nYou'll get one MCX gold briefing here every morning.",
                      token, chat_id)
    except telegram.TelegramError as e:
        return False, f"Saved, but the confirmation message failed: {e}"
    return True, f"Connected {handle} to {name or 'your chat'}. A confirmation message is on its way."


def disconnect():
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        set_env_value(key, "")
        os.environ.pop(key, None)


def setup() -> str:
    token, _ = telegram.get_config()
    if not token:
        return ("TELEGRAM_BOT_TOKEN is missing. Create a bot with @BotFather in Telegram, add the token "
                "in the dashboard's Alerts tab (or to .env), press Start in the bot, then run this again.")
    return connect(token)[1]


def schedule_command(hhmm: str = "08:30") -> str:
    return f'schtasks /Create /SC DAILY /ST {hhmm} /TN GoldLensMorning /TR "{DAILY_SCRIPT}" /F'


def main(argv=None):
    load_env()
    ap = argparse.ArgumentParser(description="GoldLens morning briefing on Telegram")
    ap.add_argument("--setup", action="store_true", help="connect the bot in .env to your chat")
    ap.add_argument("--test", action="store_true", help="send a short test message")
    ap.add_argument("--force", action="store_true", help="resend even if already sent")
    ap.add_argument("--alerts-only", action="store_true", help="only send new alerts, no morning message")
    ap.add_argument("--no-refresh", action="store_true", help="skip downloading new MCX data")
    ap.add_argument("--lang", default=os.environ.get("TELEGRAM_LANGUAGE", "English"), choices=["English", "Hindi"])
    args = ap.parse_args(argv)
    try:
        if args.setup:
            print(setup())
        elif args.test:
            telegram.send("🪙 <b>GoldLens test</b>\nTelegram alerts are working.")
            print("test message sent")
        else:
            print(run(args.lang, args.force, args.alerts_only, refresh=not args.no_refresh))
    except telegram.TelegramError as e:
        print(f"Telegram error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
