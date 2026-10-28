"""Send GoldLens briefs and alerts to Telegram through the Bot API.

Setup (once): create a bot with @BotFather, put its token in .env as TELEGRAM_BOT_TOKEN,
send any message to the bot, then run `python -m goldlens.notify --setup` to find and save
your chat id (TELEGRAM_CHAT_ID).
"""
from __future__ import annotations

import html
import os
import re

import pandas as pd
import requests

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4096  # Telegram's limit per message


class TelegramError(RuntimeError):
    pass


def get_config() -> tuple[str | None, str | None]:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip() or None
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip() or None
    return token, chat


def is_configured() -> bool:
    token, chat = get_config()
    return bool(token and chat)


def _call(token: str, method: str, **params) -> dict:
    try:
        r = requests.post(API.format(token=token, method=method), json=params, timeout=20)
    except requests.RequestException as e:
        raise TelegramError(f"could not reach Telegram ({type(e).__name__})") from e
    try:
        body = r.json()
    except ValueError as e:
        raise TelegramError(f"Telegram returned HTTP {r.status_code}") from e
    if not body.get("ok"):
        desc = body.get("description", f"HTTP {r.status_code}")
        if r.status_code == 401:
            desc = "Telegram rejected this bot token. Copy it again from @BotFather."
        elif r.status_code == 400 and "chat not found" in desc.lower():
            desc = "chat not found; send your bot a message, then run the setup again"
        raise TelegramError(desc)
    return body.get("result")


def get_me(token: str) -> dict:
    """The bot's own profile; also the cheapest way to check a token."""
    return _call(token, "getMe") or {}


def mask(token: str | None) -> str:
    if not token:
        return ""
    head, _, tail = token.partition(":")
    return f"{head}:••••{tail[-4:]}" if tail else "••••"


def find_chat_id(token: str) -> tuple[str, str] | None:
    """Chat id and name of the most recent person who messaged the bot."""
    updates = _call(token, "getUpdates") or []
    for u in reversed(updates):
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post")
        if msg and msg.get("chat"):
            chat = msg["chat"]
            name = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
            return str(chat["id"]), name
    return None


def md_to_html(text: str) -> str:
    """Telegram HTML from the simple Markdown the AI writes: bold, italics, bullets."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])_(.+?)_(?![\w*])", r"<i>\1</i>", out)
    out = re.sub(r"^\s*[-*]\s+", "• ", out, flags=re.M)
    out = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", out, flags=re.M)
    return out


def split(text: str, limit: int = MAX_LEN) -> list[str]:
    """Split on paragraph breaks so no message exceeds Telegram's limit."""
    parts, cur = [], ""
    for para in text.split("\n\n"):
        piece = para if not cur else cur + "\n\n" + para
        if len(piece) <= limit:
            cur = piece
            continue
        if cur:
            parts.append(cur)
        while len(para) > limit:
            parts.append(para[:limit])
            para = para[limit:]
        cur = para
    if cur:
        parts.append(cur)
    return parts


def send(text_html: str, token: str | None = None, chat_id: str | None = None) -> int:
    """Send an HTML message (split if long). Returns how many messages went out."""
    t, c = get_config()
    token, chat_id = token or t, chat_id or c
    if not token or not chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
    chunks = split(text_html)
    for chunk in chunks:
        _call(token, "sendMessage", chat_id=chat_id, text=chunk, parse_mode="HTML",
              disable_web_page_preview=True)
    return len(chunks)


# ---------------------------------------------------------------- message builders
STATUS_EMOJI = {"ALERT": "🟢", "Flagged, below cost": "🟡", "Normal": "⚪", "Illiquid: no signal": "⚫",
                "Market closed": "🌙"}


def _rs(x) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    sign = "−" if v < 0 else ""
    v = abs(v)
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:,.2f} lakh"
    return f"{sign}₹{v:,.0f}"


def alert_message(a: dict) -> str:
    """One actionable alert, written so it makes sense on a phone lock screen."""
    return (f"🟢 <b>GoldLens alert · {html.escape(a['pair'])}</b>\n"
            f"{html.escape(a.get('rich') or '')} looks rich vs {html.escape(a.get('cheap') or '')}: "
            f"z = <b>{a['z']:+.2f}</b> (spread {a['spread_bps']:+.1f} bps vs 60-day mean {a['mean_bps']:+.1f}).\n"
            f"Expected reversion ≈ <b>{_rs(a['edge_rs'])}</b> per 200 g pair vs {_rs(a['round_trip_cost_rs'])} "
            f"round-trip costs.\n<i>{html.escape(a['leg_a'])} vs {html.escape(a['leg_b'])} · statistical flag, not advice.</i>")


def daily_message(facts: dict, brief_md: str, alerts: list[dict], dashboard_url: str | None = None) -> str:
    m = facts["market"]
    chg = m.get("spot_change_30d_pct")
    chg_txt = f" ({'▲' if chg >= 0 else '▼'}{chg:+.2f}% in 30 d)" if chg is not None else ""
    live = [a for a in alerts if a["status"] == "ALERT"]
    flagged = [a for a in alerts if a["status"] == "Flagged, below cost"]
    scan = "\n".join(f"{STATUS_EMOJI.get(a['status'], '•')} {html.escape(a['pair'])}  z {a['z']:+.2f}"
                     for a in alerts if a.get("z") == a.get("z"))
    head = (f"🪙 <b>GoldLens daily brief · {facts['as_of']}</b>\n"
            f"Spot ₹{m['spot_implied']:,.0f}/10 g{chg_txt} · carry {m['carry_pct']:.2f}%\n"
            f"Signals: <b>{len(live)} alert</b> · {len(flagged)} flagged below cost")
    body = md_to_html(brief_md.strip())
    tail = f"<b>Scanner</b>\n<code>{scan}</code>" if scan else ""
    link = f'\n\n<a href="{html.escape(dashboard_url)}">Open the dashboard</a>' if dashboard_url else ""
    return "\n\n".join(p for p in (head, body, tail) if p) + link


def _signal_line(a: dict) -> str:
    return (f"🟢 <b>{html.escape(a['pair'])}</b>: {html.escape(a.get('rich') or '')} rich, z {a['z']:+.2f}, "
            f"edge {_rs(a['edge_rs'])} vs cost {_rs(a['round_trip_cost_rs'])}")


def morning_message(facts: dict, ctx: dict, take: str | None, alerts: list[dict],
                    dashboard_url: str | None = None) -> str:
    """The one message a trader gets each morning. Short enough to read on a lock screen."""
    m = facts["market"]
    today = ctx["today"]
    settle = pd.Timestamp(facts["as_of"])
    lines = [f"🪙 <b>GoldLens · Morning brief</b>",
             f"{today:%a %d %b %Y} · MCX settlement {settle:%d %b}", ""]

    dd, mo = ctx.get("spot_dd"), m.get("spot_change_30d_pct")
    move = []
    if dd is not None:
        move.append(f"{'▲' if dd >= 0 else '▼'}{abs(dd):.2f}% d/d")
    if mo is not None:
        move.append(f"30 d {'▲' if mo >= 0 else '▼'}{abs(mo):.2f}%")
    lines.append(f"📊 Gold <b>₹{m['spot_implied']:,.0f}</b>/10 g (999)" + (f" · {' · '.join(move)}" if move else ""))
    lines.append(f"     Carry {m['carry_pct']:.2f}% a year")
    lines.append("")

    live = [a for a in alerts if a["status"] == "ALERT"]
    if live:
        lines.append(f"🎯 <b>{len(live)} signal{'s' if len(live) > 1 else ''} today</b>")
        lines += [_signal_line(a) for a in live]
    else:
        lines.append("🎯 <b>No signal today</b>: nothing clears the cost hurdle. Quiet by design.")
        near = ctx.get("nearest")
        if near:
            lines.append(f"     Closest: {html.escape(near['pair'])} at z {near['z']:+.2f} (needs ±2)")
    prem = facts.get("premiums_bps") or {}
    if prem:
        short = {"GOLDTEN": "TEN", "GOLDGUINEA": "GUINEA", "GOLDPETAL": "PETAL", "GOLDM": "M"}
        lines.append("")
        lines.append("💎 Premium vs GOLDM: " + " · ".join(f"{short.get(k, k)} {v:+.0f}" for k, v in prem.items()) + " bps")

    if ctx.get("events"):
        lines.append("")
        lines.append("📅 <b>Coming up</b>")
        for e in ctx["events"]:
            syms = ", ".join(s.replace("GOLD", "") or "GOLD" for s in e["symbols"])
            days = (e["expiry"] - today).days
            lines.append(f"• {syms} expire {e['expiry']:%a %d %b} ({days} d); GoldLens rolls out {e['roll_out']:%d %b}")

    if take:
        lines.append("")
        lines.append(f"🧠 <b>AI take</b>: {md_to_html(take.strip())}")

    lines.append("")
    if dashboard_url:
        lines.append(f'<a href="{html.escape(dashboard_url)}">Open the dashboard</a>')
    lines.append("<i>Statistical analysis, not investment advice.</i>")
    return "\n".join(lines)
