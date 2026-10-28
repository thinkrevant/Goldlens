"""GoldLens dashboard. Run with:  streamlit run app.py"""
from __future__ import annotations

import datetime
import os
from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv(__import__('pathlib').Path(__file__).with_name('.env'), override=True)
except ImportError:
    pass

from goldlens import ai, live, notify, telegram, tipcheck, ui
from goldlens.analytics import rolldown_decomposition
from goldlens.backtest import BacktestConfig, attribution, ladder_configs, run_portfolio
from goldlens.config import LEG_GRAMS, SPECS, SYMBOLS, CostModel
from goldlens.normalise import active_contracts
from goldlens.pipeline import build_workspace, data_quality
from goldlens.signals import alerts as compute_alerts, fact_sheet
from goldlens.ui import GOLD, MUTED, UP, DOWN, BLUE, SYMBOL_COLORS as COLORS, inr

st.set_page_config(page_title="GoldLens · MCX gold intelligence", page_icon="🪙", layout="wide",
                   initial_sidebar_state="collapsed")
ui.inject()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.html(f'<div style="display:flex;gap:10px;align-items:center">{ui.LOGO_IMG}<div><b style="font-size:1.1rem">GoldLens</b>'
            f'<div style="color:{MUTED};font-size:.75rem">Controls</div></div></div>')
    language = st.segmented_control("AI analyst language", ["English", "Hindi"], default="English") or "English"
    with st.expander("Strategy parameters", expanded=False, icon=":material/tune:"):
        window = st.slider("Z-score lookback (days)", 20, 120, 60, 5)
        entry_z = st.slider("Entry |z|", 1.5, 3.5, 2.0, 0.1)
        exit_z = st.slider("Exit |z|", 0.0, 1.5, 0.5, 0.1)
        max_hold = st.slider("Max holding days", 5, 60, 20, 5)
        min_volume = st.slider("Min lots traded per leg", 0, 500, 50, 10)
        roll_bdays = st.slider("Roll out N business days before expiry", 2, 10, 5, 1)
    with st.expander("Cost assumptions", expanded=False, icon=":material/payments:"):
        slippage = st.slider("Slippage (ticks per lot per fill)", 0.0, 6.0, 2.0, 0.5)
        brokerage = st.slider("Brokerage per order (₹)", 0, 100, 20, 5)
        fees_on = st.checkbox("Exchange fees, CTT, stamp duty, GST", value=True)
        st.caption("Approximate retail rates; edit to match your broker.")
    st.caption("Parameters are fixed up front, not tuned on the results.")

base_costs = CostModel(brokerage_per_order=float(brokerage), slippage_ticks=float(slippage))
if not fees_on:
    base_costs = replace(base_costs, exchange_rate=0, sebi_rate=0, ctt_rate=0, stamp_rate=0, gst_rate=0)
base_cfg = BacktestConfig(window=window, entry_z=entry_z, exit_z=exit_z, max_hold=max_hold,
                          min_volume=float(min_volume), costs=base_costs)


# ---------------------------------------------------------------- data
@st.cache_resource(show_spinner="Loading MCX Bhavcopy history…")
def get_ws(roll: int):
    return build_workspace(roll)


@st.cache_data(show_spinner="Replaying the backtest day by day…")
def get_ladder(roll: int, cfg_key: tuple):
    ws = get_ws(roll)
    out = []
    for name, cfg in ladder_configs(base_cfg_from_key(cfg_key)):
        daily, _, tot = run_portfolio(ws.pairs, cfg, ws.prices)
        out.append((name, daily["total"], tot))
    return out


@st.cache_data(show_spinner=False)
def get_custom(roll: int, cfg_key: tuple, flags: tuple):
    ws = get_ws(roll)
    cfg = replace(base_cfg_from_key(cfg_key), **dict(flags))
    daily, results, tot = run_portfolio(ws.pairs, cfg, ws.prices)
    return daily, results, tot


def cfg_key(cfg: BacktestConfig) -> tuple:
    c = cfg.costs
    return (cfg.window, cfg.entry_z, cfg.exit_z, cfg.max_hold, cfg.min_volume,
            c.brokerage_per_order, c.exchange_rate, c.sebi_rate, c.ctt_rate, c.stamp_rate,
            c.gst_rate, c.slippage_ticks)


def base_cfg_from_key(k: tuple) -> BacktestConfig:
    return BacktestConfig(window=k[0], entry_z=k[1], exit_z=k[2], max_hold=k[3],
                          min_volume=k[4], costs=CostModel(*k[5:]))


ws = get_ws(roll_bdays)
KEY = cfg_key(base_cfg)
ladder = get_ladder(roll_bdays, KEY)
honest_daily, honest_results, honest_tot = get_custom(roll_bdays, KEY, ())
alert_rows = compute_alerts(ws.pairs, base_cfg)
facts = fact_sheet(ws.curves, alert_rows, honest_tot, [(n, t) for n, _, t in ladder])
as_of = facts["as_of"]
last_day = ws.df["date"].max()

# Today's active contract per symbol, with day change and a 60-day normalised sparkline.
act_today = active_contracts(ws.df, roll_bdays).xs(last_day, level="date")
latest_curve = ws.curves.iloc[-1]
watch = []
for sym in SYMBOLS:
    if sym not in act_today.index:
        continue
    r = act_today.loc[sym]
    hist = ws.front.xs(sym, level="symbol")["px10"].tail(60)
    watch.append({
        "symbol": sym, "contract": r["contract"].split(" ", 1)[1], "quoted": r["close"], "px10": r["px10"],
        "chg": (r["close"] / r["prev_close"] - 1) * 100 if r["prev_close"] else 0.0,
        "premium": None if sym == "GOLDM" else latest_curve.get(f"premium_{sym}"),
        "volume": r["volume"], "oi": r["oi"], "spark": hist.tolist(),
    })

# ---------------------------------------------------------------- header + ticker
ui.header(as_of=pd.Timestamp(as_of).strftime("%d %b %Y"),
          data_span=f"{ws.df['date'].min():%b %Y} – {last_day:%b %Y}",
          ai_label=(ai.last_used or " → ".join(ai.LABELS[p] for p in ai.chain())) if ai.chain() else "template",
          ai_on=ai.has_key(), live_on=bool(live.get_token()))
m = facts["market"]
n_alert = sum(a["status"] == "ALERT" for a in alert_rows)
n_flag = sum(a["status"] == "Flagged, below cost" for a in alert_rows)
nxt = ws.calendar[ws.calendar["expiry"] >= last_day].sort_values("expiry").iloc[0]
ui.ticker([{"sym": w["symbol"], "sub": w["contract"], "px": f"₹{w['px10']:,.0f}", "chg": w["chg"]} for w in watch] + [
    {"sym": "SPOT", "sub": "implied · 999", "px": f"₹{m['spot_implied']:,.0f}", "chg": m["spot_change_30d_pct"]},
    {"sym": "CARRY", "sub": "annualised", "px": f"{m['carry_pct']:.2f}%"},
    {"sym": "SIGNALS", "sub": "today", "px": f"{n_alert} alert · {n_flag} flagged"},
    {"sym": "NEXT EXPIRY", "sub": nxt["contract"], "px": f"{(nxt['expiry'] - last_day).days} days"},
    {"sym": "HONEST P&L", "sub": "after costs", "px": inr(honest_tot["net_pnl"], signed=True)},
])

tabs = st.tabs([":material/space_dashboard: Overview", ":material/sensors: Live",
                ":material/notifications_active: Alerts", ":material/radar: Scanner",
                ":material/show_chart: Curve & carry", ":material/science: Backtest",
                ":material/fact_check: Tip Checker", ":material/calendar_month: Calendar", ":material/verified: Data quality",
                ":material/forum: Ask GoldLens"])

# ================================================================ Overview
with tabs[0]:
    eq = honest_daily["total"].cumsum()
    sig_hist = pd.concat({k: r.signal["z"].abs() >= entry_z for k, r in honest_results.items()}, axis=1)
    sig_count = sig_hist.sum(axis=1).tail(120)
    ui.kpis([
        {"label": "Implied spot · ₹/10 g 999", "value": f"₹{m['spot_implied']:,.0f}", "accent": True,
         "sub": (f'<span class="{ui.tone(m["spot_change_30d_pct"])}">{ui.arrow(m["spot_change_30d_pct"])} '
                 f'{m["spot_change_30d_pct"]:+.2f}%</span> in 30 days') if m["spot_change_30d_pct"] is not None else "",
         "spark": ws.curves["spot_implied"].tail(120).tolist()},
        {"label": "Futures carry · annualised", "value": f"{m['carry_pct']:.2f}%", "color": BLUE,
         "sub": "what the market charges to hold gold forward", "spark": (ws.curves["carry"] * 100).tail(120).tolist()},
        {"label": "Signals today", "value": f"{n_alert}<span style='color:{MUTED};font-size:1rem'> / {len(alert_rows)}</span>",
         "sub": f"{n_flag} flagged but below cost · quiet by design", "spark": sig_count.tolist(), "color": "#A78BFA"},
        {"label": "Honest backtest · net", "value": f'<span class="{ui.tone(honest_tot["net_pnl"])}">{inr(honest_tot["net_pnl"], signed=True)}</span>',
         "sub": f"{honest_tot['trades']} trades · Sharpe {ui.num(honest_tot['sharpe'])} · after {inr(honest_tot['costs'])} costs",
         "spark": eq.tolist(), "color": UP if honest_tot["net_pnl"] >= 0 else DOWN},
    ])

    left, right = st.columns([5, 3], gap="medium")
    with left:
        ui.market_watch(watch, f"Market watch · active contracts · {pd.Timestamp(as_of):%d %b %Y}")
    with right:
        with st.container():
            st.html(f'<div class="gl-brief"><div class="hd"><span class="ttl">✦ AI daily brief</span>'
                    f'<span class="by">{"Grounded in today\'s computed numbers" if ai.has_key() else "Template mode"}</span></div>'
                    f'<div class="foot">Every figure comes from the GoldLens fact sheet. The model explains; it never calculates.</div></div>')
            if st.button("Write today's brief", type="primary", key="brief_btn", width="stretch",
                         icon=":material/auto_awesome:") or "brief" in st.session_state:
                if st.session_state.get("brief_lang") != language or "brief" not in st.session_state:
                    st.session_state["brief"] = st.write_stream(ai.stream("brief", facts, language))
                    st.session_state["brief_lang"] = language
                    st.session_state["brief_by"] = ai.last_used
                else:
                    st.markdown(st.session_state["brief"])
                if st.session_state.get("brief_by") and "Template brief" not in st.session_state["brief"]:
                    st.caption(f"Written by {st.session_state['brief_by']} · {language}")
            elif not ai.has_key():
                st.caption("No AI key in .env: the brief uses GoldLens's built-in template.")

    ui.section("Same gold. Four contracts. Four prices.",
               "Flip the switch: GoldLens converts every price to ₹ per 10 g of 999 gold, and four "
               "unrelated-looking lines collapse into one. The small gaps left over are the signal.", "The core idea")
    view = st.segmented_control("View", ["As quoted on MCX", "Normalised by GoldLens"],
                                default="Normalised by GoldLens", label_visibility="collapsed", key="norm_view")
    fr = ws.front.reset_index()
    fr = fr[fr["date"] >= last_day - pd.Timedelta(days=365)]
    ycol, ylab = ("close", "Quoted price (₹)") if view == "As quoted on MCX" else ("px10", "₹ per 10 g of 999 gold")
    fig = go.Figure()
    for sym in SYMBOLS:
        s = fr[fr["symbol"] == sym]
        fig.add_trace(go.Scatter(x=s["date"], y=s[ycol], name=sym, mode="lines",
                                 line=dict(color=COLORS[sym], width=1.8)))
    fig.update_layout(yaxis_title=ylab, yaxis_tickformat=",.0f")
    ui.chart(fig, 400)
    st.caption("Normalisation: price × (10 / quoted grams) × (999 / purity). GOLDGUINEA is quoted per 8 g, "
               "GOLDPETAL per 1 g, GOLDM at 995 purity.")

# ================================================================ Live
with tabs[1]:
    ui.section("Live scanner", "Live MCX quotes from Upstox, scored against the same past-only statistics as the daily "
               "scanner. The cost hurdle uses the real order book: buy at the ask, sell at the bid.", "Real time")
    auto = st.toggle(f"Auto-refresh every {live.refresh_seconds()} s", value=True, key="live_auto")

    @st.fragment(run_every=live.refresh_seconds() if auto else None)
    def live_panel():
        snap = live.snapshot(roll_bdays)
        if snap.ok:
            settle = ws.df[ws.df["date"] == last_day].set_index("contract")["px10"]
            q = snap.quotes.copy()
            q["vs_settle_pct"] = (q["px10"] / q["contract"].map(settle) - 1) * 100
            if q["vs_settle_pct"].abs().max() > 8:
                snap.ok = False
                snap.message = ("Unit check failed: live prices differ from the last settlement by more than 8%, "
                                "so they are not scored. Showing the daily scanner.")
        if not snap.ok:
            st.info(snap.message, icon=":material/event:")
            ui.scanner_cards(alert_rows, entry_z)
            if not live.get_token():
                st.html('<div class="gl-panel" style="margin-top:12px"><h4>Turn on live data</h4>'
                        '<div class="foot">Free Upstox account → <b>Developer Apps</b> → <b>Analytics</b> tab → '
                        '<b>Generate Token</b>, then add <code>UPSTOX_ANALYTICS_TOKEN=…</code> to <code>.env</code>. '
                        'Read-only, valid for a year.</div></div>')
            return
        (st.warning if snap.stale else st.success)(snap.message, icon=":material/schedule:" if snap.stale else ":material/bolt:")
        ui.scanner_cards(live.live_alerts(snap, ws.pairs, ws.curves, base_cfg, roll_bdays), entry_z)
        show = q.sort_values(["symbol", "expiry"])[
            ["contract", "bid", "ask", "last_price", "px10", "vs_settle_pct", "volume", "oi", "last_trade_time"]]
        st.dataframe(show, hide_index=True, width="stretch", column_config={
            "px10": st.column_config.NumberColumn("₹/10 g 999 (mid)", format="%,.0f"),
            "vs_settle_pct": st.column_config.NumberColumn("vs last settlement", format="%+.2f%%"),
            "last_price": st.column_config.NumberColumn("Last", format="%,.0f"),
            "last_trade_time": st.column_config.DatetimeColumn("Last trade (IST)", format="DD MMM HH:mm:ss")})
        carry_txt = f"{snap.carry * 100:.2f}% live carry" if snap.carry is not None else "carry from last settlement"
        st.caption(f"Fetched {snap.fetched_at:%H:%M:%S} IST · {carry_txt}")

    live_panel()

# ================================================================ Alerts
def _is_local() -> bool:
    """Settings that write to .env are only offered on the machine running GoldLens."""
    try:
        host = (st.context.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    except Exception:
        host = ""
    return host in ("127.0.0.1", "localhost", "::1") or host.endswith(".localhost")


def _bot_info(token: str) -> dict:
    cache = st.session_state.setdefault("tg_bot_cache", {})
    if token not in cache:
        try:
            cache[token] = telegram.get_me(token)
        except telegram.TelegramError as e:
            cache[token] = {"error": str(e)}
    return cache[token]


with tabs[2]:
    ui.section("Morning briefing on Telegram",
               "One message every morning: the gold price, today's signals, premiums vs GOLDM, upcoming expiries and "
               "a short AI take. Connect your own Telegram bot in under a minute.", "Alerts")
    local = _is_local()
    tg_token, tg_chat = telegram.get_config()
    tg_lang = os.environ.get("TELEGRAM_LANGUAGE", "English")
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        flash = st.session_state.pop("tg_flash", None)
        if flash:
            (st.success if flash[0] else st.warning)(flash[1], icon=":material/check_circle:" if flash[0] else ":material/info:")

        if telegram.is_configured():
            info = _bot_info(tg_token)
            name = f"@{info['username']}" if info.get("username") else "your bot"
            st.html(f'<div class="gl-panel"><h4>Connection</h4><div style="display:flex;align-items:center;gap:10px">'
                    f'<span class="dot live"></span><b style="font-size:1rem">Connected to {ui.esc(name)}</b></div>'
                    f'<div class="foot">Token {ui.esc(telegram.mask(tg_token))} · chat {ui.esc(tg_chat)} · '
                    f'language {ui.esc(tg_lang)}</div>'
                    + (f'<div class="foot" style="color:var(--down)">{ui.esc(info["error"])}</div>' if info.get("error") else "")
                    + '</div>')
            b1, b2, b3 = st.columns([1.4, 1, 1])
            if b1.button("Send today's message now", type="primary", icon=":material/send:", width="stretch"):
                with st.spinner("Writing the AI take and sending…"):
                    try:
                        st.session_state["tg_flash"] = (True, notify.send_morning(ws, alert_rows, facts, tg_lang))
                    except telegram.TelegramError as e:
                        st.session_state["tg_flash"] = (False, f"Telegram: {e}")
                st.rerun()
            if b2.button("Send test", icon=":material/notifications:", width="stretch"):
                try:
                    telegram.send("🪙 <b>GoldLens test</b>\nTelegram alerts are working.")
                    st.session_state["tg_flash"] = (True, "Test message sent.")
                except telegram.TelegramError as e:
                    st.session_state["tg_flash"] = (False, f"Telegram: {e}")
                st.rerun()
            if b3.button("Disconnect", icon=":material/link_off:", width="stretch", disabled=not local):
                notify.disconnect()
                st.session_state["tg_flash"] = (True, "Disconnected. The token was removed from .env.")
                st.rerun()
        else:
            st.html('<div class="gl-panel"><h4>Connect in 4 steps</h4><div class="foot" style="line-height:1.9">'
                    '<b>1.</b> In Telegram, open <b>@BotFather</b> and send <code>/newbot</code><br>'
                    '<b>2.</b> Pick a name; BotFather replies with a <b>token</b>. Paste it below<br>'
                    '<b>3.</b> Open your new bot and press <b>Start</b><br>'
                    '<b>4.</b> Click <b>Connect</b>. GoldLens finds your chat and sends a hello</div></div>')
            if not local:
                st.info("Connecting a bot is only available on the computer running GoldLens.", icon=":material/lock:")
            with st.form("tg_connect", border=False):
                token_in = st.text_input("Bot token", type="password", placeholder="123456789:AAH…",
                                         value=tg_token or "", disabled=not local,
                                         help="Stored only in this computer's .env file. Never shown in full.")
                if st.form_submit_button("Connect", type="primary", icon=":material/link:", disabled=not local):
                    with st.spinner("Checking the token…"):
                        ok, msg = notify.connect(token_in)
                    st.session_state["tg_flash"] = (ok, msg)
                    st.session_state.pop("tg_bot_cache", None)
                    st.rerun()

        with st.container(border=True):
            st.markdown("**Send it every morning**")
            c1, c2 = st.columns(2)
            when = c1.time_input("Send time", value=datetime.time(8, 30), step=900, key="tg_time")
            lang_pick = c2.segmented_control("Language", ["English", "Hindi"], default=tg_lang, key="tg_lang_pick",
                                             disabled=not local) or tg_lang
            if local and lang_pick != tg_lang:
                notify.set_env_value("TELEGRAM_LANGUAGE", lang_pick)
                os.environ["TELEGRAM_LANGUAGE"] = lang_pick
                st.rerun()
            st.caption("Run this once in a terminal. Windows then refreshes the MCX data and sends the message daily "
                       "(your PC needs to be on at that time):")
            st.code(notify.schedule_command(when.strftime("%H:%M")), language="bash")

    with right:
        preview, by = notify.build_morning(ws, alert_rows, facts, tg_lang, use_ai=False)
        ui.phone(preview, _bot_info(tg_token).get("first_name") if telegram.is_configured() else "GoldLens Bot",
                 when.strftime("%H:%M"))
        if "AI take" not in preview:
            if st.button("Add the AI take to this preview", icon=":material/auto_awesome:", width="stretch",
                         disabled=not ai.has_key()):
                with st.spinner("Writing the AI take…"):
                    ai.complete("morning", facts, tg_lang)
                st.rerun()
            st.caption("The AI take is written fresh each morning when the message is sent.")

# ================================================================ Scanner
with tabs[3]:
    ui.section("Relative-value scanner",
               f"An alert needs |z| ≥ {entry_z:g}, both legs traded in size, and an expected reversion worth at least "
               f"1.5× round-trip costs on a {LEG_GRAMS:.0f} g pair. The gold tick on each meter is that hurdle.",
               f"Settlement {pd.Timestamp(as_of):%d %b %Y}")
    ui.scanner_cards(alert_rows, entry_z)

    ui.section("Pair inspector", "Carry-adjusted spread with its rolling mean, entry band, and every honest-backtest trade.")
    pair_names = [f"{a}/{b}" for a, b in ws.pairs]
    default = alert_rows[0]["pair"] if alert_rows else pair_names[0]
    pick = st.pills("Pair", pair_names, default=default, label_visibility="collapsed", key="pair_pick") or default
    key = tuple(pick.split("/"))
    res = honest_results[key]
    sig = res.signal
    mean = sig["spread"].shift(1).rolling(window, min_periods=window // 2).mean()
    sd = sig["spread"].shift(1).rolling(window, min_periods=window // 2).std()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sig.index, y=mean + entry_z * sd, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=sig.index, y=mean - entry_z * sd, line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(224,176,74,0.10)", name=f"±{entry_z:g}σ band", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=sig.index, y=mean, line=dict(color=GOLD, dash="dot", width=1), name="Rolling mean"))
    fig.add_trace(go.Scatter(x=sig.index, y=sig["spread"], line=dict(color=BLUE, width=1.5), name="Spread (bps)"))
    if not res.trades.empty:
        t = res.trades
        fig.add_trace(go.Scatter(x=t["entry_date"], y=sig["spread"].reindex(t["entry_date"]).to_numpy(), mode="markers",
                                 name="Entry", marker=dict(symbol="triangle-up", size=10, color=UP, line=dict(width=0))))
        fig.add_trace(go.Scatter(x=t["exit_date"], y=sig["spread"].reindex(t["exit_date"]).to_numpy(), mode="markers",
                                 name="Exit", marker=dict(symbol="x-thin", size=9, color=DOWN, line=dict(width=2, color=DOWN))))
    fig.update_layout(yaxis_title=f"ln({key[0]} / {key[1]}) after carry · bps")
    ui.chart(fig, 400)
    pm = res.metrics
    ui.kpis([
        {"label": "Net P&L · honest", "value": f'<span class="{ui.tone(pm["net_pnl"])}">{inr(pm["net_pnl"], signed=True)}</span>',
         "sub": f"{pm['ann_return_pct']:+.2f}% a year on one-leg notional", "spark": res.daily["net"].cumsum().tolist(),
         "color": UP if pm["net_pnl"] >= 0 else DOWN},
        {"label": "Gross before costs", "value": inr(pm["gross_pnl"], signed=True), "sub": "spread P&L on held contracts"},
        {"label": "Costs paid", "value": inr(pm["costs"]), "sub": "fees, taxes, slippage, rolls"},
        {"label": "Trades · win rate", "value": f"{pm['trades']} · {pm['win_rate'] * 100:.0f}%",
         "sub": f"Sharpe {ui.num(pm['sharpe'])} · max DD {inr(pm['max_drawdown'])}"},
    ])
    sel = next(a for a in alert_rows if a["pair"] == pick)
    if st.button(f"Explain {pick} with the AI analyst", icon=":material/auto_awesome:"):
        with st.container(border=True):
            st.write_stream(ai.stream("alert", {**sel, "pair_backtest": pm}, language))

    ui.section("Who trades rich?", "Premium of each contract over GOLDM after units, purity and carry are removed "
               "(5-day median). Retail demand pushed the small contracts 200-450 bps rich in early 2026.")
    prem_cols = [c for c in ws.curves.columns if c.startswith("premium_")]
    prem = ws.curves[prem_cols].rename(columns=lambda c: c.replace("premium_", "")).rolling(5, min_periods=1).median()
    fig = go.Figure()
    for sym in prem.columns:
        fig.add_trace(go.Scatter(x=prem.index, y=prem[sym], name=sym, line=dict(color=COLORS[sym], width=1.6)))
    fig.add_hline(y=0, line_color=GOLD, line_dash="dot", annotation_text="GOLDM", annotation_font_color=GOLD)
    fig.update_layout(yaxis_title="bps vs GOLDM")
    ui.chart(fig, 340)

# ================================================================ Curve & carry
with tabs[4]:
    dates = ws.curves.index
    ui.section("Term structure", "Every traded contract on one fair curve: ln(price) = ln(spot) + carry × time-to-expiry "
               "+ a premium per contract type.", "Curve & carry")
    day = st.select_slider("Curve date", options=list(dates), value=dates[-1],
                           format_func=lambda d: d.strftime("%d %b %Y"), label_visibility="collapsed")
    snap_df = ws.df[(ws.df["date"] == day) & ws.df["traded"]]
    crow = ws.curves.loc[day]
    ui.kpis([
        {"label": "Implied carry", "value": f"{crow['carry'] * 100:.2f}%", "sub": "per year", "color": BLUE,
         "spark": (ws.curves["carry"].loc[:day].tail(90) * 100).tolist()},
        {"label": "Implied spot · ₹/10 g 999", "value": f"₹{crow['spot_implied']:,.0f}", "accent": True,
         "spark": ws.curves["spot_implied"].loc[:day].tail(90).tolist()},
        {"label": "Curve fit error", "value": f"{crow['fit_rmse_bps']:.1f} bps", "sub": "volume-weighted RMSE"},
        {"label": "Contracts on the curve", "value": f"{int(crow['n'])}", "sub": "traded that day"},
    ])
    fig = go.Figure()
    taus = np.linspace(0, max(snap_df["tau"].max(), 0.1), 60)
    fig.add_trace(go.Scatter(x=day + pd.to_timedelta(taus * 365, unit="D"), y=np.exp(crow["ln_s"] + crow["carry"] * taus),
                             name="Fair curve (GOLDM basis)", line=dict(color=GOLD, dash="dash", width=1.5)))
    for sym in SYMBOLS:
        s = snap_df[snap_df["symbol"] == sym]
        if s.empty:
            continue
        fig.add_trace(go.Scatter(x=s["expiry"], y=s["px10"], mode="markers", name=sym,
                                 marker=dict(color=COLORS[sym], size=np.clip(np.sqrt(s["volume"]) / 4, 7, 26),
                                             opacity=.8, line=dict(width=1, color="#0A0D14")),
                                 customdata=s[["contract", "volume"]], hovertemplate="%{customdata[0]}<br>₹%{y:,.0f}<br>vol %{customdata[1]:,.0f}<extra></extra>"))
    fig.update_layout(yaxis_title="₹ per 10 g of 999 gold", yaxis_tickformat=",.0f", hovermode="closest")
    ui.chart(fig, 420)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        fig = go.Figure(go.Scatter(x=ws.curves.index, y=ws.curves["carry"] * 100, line=dict(color=BLUE, width=1.5),
                                   fill="tozeroy", fillcolor="rgba(91,141,239,.08)", name="carry"))
        fig.update_layout(title="Market-implied carry, % a year", showlegend=False)
        ui.chart(fig, 300)
    with c2:
        span = st.select_slider("Period", options=list(dates), value=(dates[max(0, len(dates) - 22)], dates[-1]),
                                format_func=lambda d: d.strftime("%d %b %y"))
        tau_days = st.slider("Contract's days to expiry at start", 15, 180, 60, 5)
        dec = rolldown_decomposition(ws.curves, tau_days / 365, span[0], span[1])
        if dec:
            fig = go.Figure(go.Waterfall(x=["Spot shift", "Carry change", "Roll-down", "Total"],
                                         y=[dec["level_bps"], dec["carry_shift_bps"], dec["rolldown_bps"], dec["total_bps"]],
                                         measure=["relative", "relative", "relative", "total"],
                                         increasing=dict(marker_color=UP), decreasing=dict(marker_color=DOWN),
                                         totals=dict(marker_color=GOLD), connector=dict(line=dict(color="#3A4458"))))
            fig.update_layout(title="Why the contract moved, bps", showlegend=False, hovermode="closest")
            ui.chart(fig, 300)
            st.caption(f"Over {dec['days']} days, {dec['rolldown_bps']:+.0f} bps came just from time passing "
                       "(futures converge to spot); the rest from gold itself and the carry rate.")

# ================================================================ Backtest
with tabs[5]:
    ui.section("Where does a backtest's edge come from?",
               f"The same strategy replayed with one common flaw removed at each step, net P&L over all {len(ws.pairs)} "
               f"pairs at {LEG_GRAMS:.0f} g per leg. Watch the edge evaporate.", "The honesty test")
    notes = {"Naive": "1 lot vs 1 lot, stitched series, same-day fill, no costs",
             "+ gram-matched sizing": "a spread, not a gold bet",
             "+ fill next day": "can't trade at the price that made the signal",
             "+ past-only z-score": "no peeking at the future mean",
             "+ real contracts & carry": "no fake jumps at expiry",
             "+ costs": "brokerage, fees, CTT, stamp, GST, slippage",
             "+ liquidity filter (honest)": "no trading on stale prices"}
    ui.funnel([(n, notes.get(n, ""), t["net_pnl"]) for n, _, t in ladder])
    eq = pd.concat({n: s.cumsum() for n, s, _ in ladder}, axis=1)
    fig = go.Figure()
    for i, c in enumerate(eq.columns):
        last = i == len(eq.columns) - 1
        fig.add_trace(go.Scatter(x=eq.index, y=eq[c], name=c,
                                 line=dict(width=3 if last else 1.1, color=GOLD if last else None),
                                 opacity=1 if last else .55))
    fig.update_layout(title="Cumulative net P&L for each step (₹)", yaxis_tickformat=",.0f",
                      legend=dict(font=dict(size=10)))
    ui.chart(fig, 400)

    ui.section("Run your own", "Switch any fix off to see how much fake edge it creates.")
    cols = st.columns(6)
    flags = (("gram_matched", cols[0].toggle("Gram-matched", True)),
             ("next_day_fill", cols[1].toggle("Fill T+1", True)),
             ("rolling_stats", cols[2].toggle("Past-only stats", True)),
             ("true_contracts", cols[3].toggle("Real contracts", True)),
             ("apply_costs", cols[4].toggle("Costs", True)),
             ("liquidity_filter", cols[5].toggle("Liquidity filter", True)))
    daily, results, tot = get_custom(roll_bdays, KEY, flags)
    ui.kpis([
        {"label": "Net P&L", "value": f'<span class="{ui.tone(tot["net_pnl"])}">{inr(tot["net_pnl"], signed=True)}</span>',
         "spark": daily["total"].cumsum().tolist(), "color": UP if tot["net_pnl"] >= 0 else DOWN,
         "sub": f"{tot['trades']} trades"},
        {"label": "Gross before costs", "value": inr(tot["gross_pnl"], signed=True), "sub": "what most backtests report"},
        {"label": "Costs", "value": inr(tot["costs"]), "sub": "every fill, every roll"},
        {"label": "Sharpe · max drawdown", "value": ui.num(tot["sharpe"]), "sub": f"max DD {inr(tot['max_drawdown'])}"},
    ])
    per = pd.DataFrame([{"Pair": f"{a}/{b}", **{k: r.metrics[k] for k in
                         ("net_pnl", "gross_pnl", "costs", "trades", "win_rate", "sharpe", "max_drawdown", "ann_return_pct")}}
                        for (a, b), r in results.items()]).sort_values("net_pnl", ascending=False)
    st.dataframe(per, hide_index=True, width="stretch", column_config={
        "net_pnl": st.column_config.NumberColumn("Net ₹", format="%,.0f"),
        "gross_pnl": st.column_config.NumberColumn("Gross ₹", format="%,.0f"),
        "costs": st.column_config.NumberColumn("Costs ₹", format="%,.0f"),
        "trades": st.column_config.NumberColumn("Trades"),
        "win_rate": st.column_config.ProgressColumn("Win rate", min_value=0, max_value=1, format="percent"),
        "sharpe": st.column_config.NumberColumn("Sharpe", format="%.2f"),
        "max_drawdown": st.column_config.NumberColumn("Max DD ₹", format="%,.0f"),
        "ann_return_pct": st.column_config.NumberColumn("Return / yr", format="%.2f%%")})

    ui.section("Honest attribution: strategy, or just gold?",
               "Daily P&L regressed on the rupee move of holding gold outright (HAC errors). A real spread strategy "
               "should carry almost no gold exposure.")
    gold = ws.front.xs("GOLDM", level="symbol")["px10"]
    a_custom = attribution(daily["total"], gold)
    a_naive = attribution(ladder[0][1], gold)
    scale = max(abs(a_naive["beta_grams"]), abs(a_custom["beta_grams"]), 1)
    ui.versus(
        {"label": "Naive backtest", "value": f'{a_naive["beta_grams"]:+.0f} g of gold',
         "sub": f"R² vs gold {a_naive['r2']:.2f}: its 'edge' is mostly a bet on gold",
         "pct": abs(a_naive["beta_grams"]) / scale * 100, "color": DOWN},
        {"label": "This run", "value": f'{a_custom["beta_grams"]:+.0f} g of gold',
         "sub": f"R² vs gold {a_custom['r2']:.2f}: P&L comes from the spread, not gold's direction",
         "pct": abs(a_custom["beta_grams"]) / scale * 100, "color": UP})
    with st.expander("Trade log", icon=":material/receipt_long:"):
        tl = pd.concat([r.trades.assign(pair=f"{a}/{b}") for (a, b), r in results.items() if not r.trades.empty],
                       ignore_index=True)
        if not tl.empty:
            st.dataframe(tl.sort_values("entry_date", ascending=False), hide_index=True, width="stretch")
            st.download_button("Download trades (CSV)", tl.to_csv(index=False), "goldlens_trades.csv",
                               icon=":material/download:")

# ================================================================ Tip Checker
TIP_EXAMPLES = ["“PETAL 1% cheaper, 40% guaranteed”", "“Guinea premium, 5% monthly”", "“2-sigma TEN vs GUINEA”"]


@st.cache_data(show_spinner=False)
def tip_eval(roll: int, cfg_k: tuple, rule_k: tuple, claimed, flags: tuple, source: str):
    rule = tipcheck.Rule(*rule_k, claimed_annual_pct=claimed, source=source, red_flags=list(flags))
    return tipcheck.evaluate(rule, get_ws(roll), base_cfg_from_key(cfg_k))


with tabs[6]:
    ui.section("Tip Checker", "Paste any tip about MCX gold contracts, from Telegram, Instagram or a friend. GoldLens turns it "
               "into a precise rule, tests it the way tipsters usually do, then tests it honestly on "
               f"{ws.df['date'].nunique()} trading days of real MCX data.", "A lie detector for trading tips")
    ex = st.pills("Examples", TIP_EXAMPLES, label_visibility="collapsed", key="tc_example")
    if ex and st.session_state.get("tc_last_example") != ex:
        st.session_state["tc_text"] = tipcheck.EXAMPLES[TIP_EXAMPLES.index(ex)]
        st.session_state["tc_last_example"] = ex
    tip = st.text_area("Tip", key="tc_text", height=90, label_visibility="collapsed",
                       placeholder="e.g. Buy GOLDPETAL when it's 1% cheaper than GOLDM, sell when it comes back. 40% a year guaranteed!")
    if st.button("Check this tip", type="primary", icon=":material/fact_check:", disabled=not (tip or "").strip()):
        with st.spinner("Reading the tip…"):
            parsed = tipcheck.parse_tip(tip)
        if parsed is None or "out of scope" in parsed.notes:
            st.session_state.pop("tc_meta", None)
            st.warning("GoldLens can only check tips about the price gap between MCX gold contracts "
                       "(GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL). This one is out of scope, so it isn't guessed at.",
                       icon=":material/block:")
        else:
            st.session_state.update({"tc_a": parsed.buy_leg, "tc_b": parsed.other_leg, "tc_side": parsed.side,
                                     "tc_mode": parsed.mode, "tc_entry": float(parsed.entry), "tc_exit": float(parsed.exit),
                                     "tc_hold": int(parsed.max_hold), "tc_claim": float(parsed.claimed_annual_pct or 0)})
            st.session_state["tc_meta"] = {"source": parsed.source, "notes": parsed.notes, "flags": parsed.red_flags}

    if "tc_meta" in st.session_state:
        meta = st.session_state["tc_meta"]
        side_lbl = {"long_a": "Buy A when cheap", "short_a": "Sell A when rich", "both": "Both directions"}
        mode_lbl = {"level": "bps gap", "z": "z-score"}
        with st.container(border=True):
            c = st.columns([1.2, 1.2, 1.6, 1.2])
            a = c[0].selectbox("Leg A (traded on the signal)", SYMBOLS, key="tc_a")
            b_opts = [x for x in SYMBOLS if x != a]
            if st.session_state.get("tc_b") not in b_opts:
                st.session_state["tc_b"] = b_opts[0]
            b = c[1].selectbox("Leg B (the comparison)", b_opts, key="tc_b")
            side = c[2].segmented_control("Direction", list(side_lbl), format_func=side_lbl.get, key="tc_side") or "long_a"
            mode = c[3].segmented_control("Threshold in", list(mode_lbl), format_func=mode_lbl.get, key="tc_mode") or "level"
            c2 = st.columns(4)
            unit = "bps (100 = 1%)" if mode == "level" else "σ"
            entry = c2[0].number_input(f"Enter when gap passes, {unit}", min_value=0.1,
                                       step=10.0 if mode == "level" else 0.1, key="tc_entry")
            exit_ = c2[1].number_input(f"Exit when gap is back to, {unit}", min_value=0.0,
                                       step=5.0 if mode == "level" else 0.1, key="tc_exit")
            hold = c2[2].number_input("Max holding days", min_value=1, max_value=120, step=1, key="tc_hold")
            claim = c2[3].number_input("Claimed return, % a year", min_value=0.0, step=5.0, key="tc_claim")
        rule = tipcheck.Rule(a, b, side, mode, float(entry), float(min(exit_, entry * 0.95)), int(hold),
                             claim or None, meta["source"])
        ui.rulebox(rule.describe(), meta["source"])
        for n in meta["notes"]:
            st.caption(f"Assumption: {n}")
        ev = tip_eval(roll_bdays, KEY, (rule.buy_leg, rule.other_leg, rule.side, rule.mode, rule.entry, rule.exit,
                                        rule.max_hold), rule.claimed_annual_pct, tuple(meta["flags"]), meta["source"])
        kind, title, detail = ev["verdict"]
        ui.verdict(kind, title, detail, meta["flags"])
        nv, hn = ev["naive"], ev["honest"]
        ui.kpis([
            {"label": "Claimed", "value": f"{claim:.0f}% / yr" if claim else "not stated", "sub": "what the tip promises"},
            {"label": "Tipster-style test", "value": f'<span class="{ui.tone(nv["ann_pct"])}">{nv["ann_pct"]:+.1f}% / yr</span>',
             "sub": f"{nv['trades']} trades · no costs, perfect fills, stitched prices",
             "spark": nv["result"].daily["net"].cumsum().tolist(), "color": MUTED},
            {"label": "Honest test", "value": f'<span class="{ui.tone(hn["ann_pct"])}">{hn["ann_pct"]:+.1f}% / yr</span>',
             "sub": f"{hn['trades']} trades · real contracts, costs, next-day fills",
             "spark": hn["result"].daily["net"].cumsum().tolist(), "color": UP if hn["ann_pct"] > 0 else DOWN, "accent": True},
            {"label": "Hidden gold bet", "value": f'{ev["attr_naive"]["beta_grams"]:+.0f} g → {ev["attr_honest"]["beta_grams"]:+.0f} g',
             "sub": "gold exposure: tipster-style vs honest"},
        ])
        left, right = st.columns([1, 1], gap="medium")
        with left:
            if ev["breakdown"]:
                ui.breakdown(ev["breakdown"])
            else:
                st.html('<div class="gl-panel"><h4>Where the paper profit went</h4><div class="foot">No step removed profit: '
                        'the rule did as well tested honestly as it did naively.</div></div>')
        with right:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=nv["result"].daily.index, y=nv["result"].daily["net"].cumsum(), name="Tipster-style",
                                     line=dict(color=MUTED, width=1.4, dash="dot")))
            fig.add_trace(go.Scatter(x=hn["result"].daily.index, y=hn["result"].daily["net"].cumsum(), name="Honest",
                                     line=dict(color=GOLD, width=2.6)))
            fig.update_layout(title="Cumulative P&L, ₹", yaxis_tickformat=",.0f")
            ui.chart(fig, 300, key="tip_equity")
        with st.expander("Every step of the honesty test", icon=":material/stairs:"):
            ui.funnel([(s_["name"], tipcheck.REASONS.get(s_["name"], "the tip exactly as stated"), s_["net"])
                       for s_ in ev["steps"]])
        st.caption(f"Tested on {ev['first']:%d %b %Y} – {ev['last']:%d %b %Y}, {LEG_GRAMS:.0f} g per leg in the honest test. "
                   "Returns are on the larger leg's notional, unlevered. Educational tool, not investment advice.")

# ================================================================ Calendar
with tabs[7]:
    ui.section("Contract lifecycle", f"Listing to expiry for every contract. GoldLens always exits {roll_bdays} business "
               "days before expiry, ahead of the tender/delivery period (red tick), and re-enters the next contract.",
               "Calendar")
    cal = ws.calendar
    recent = cal[cal["expiry"] >= last_day - pd.Timedelta(days=200)].sort_values(["symbol", "expiry"]).copy()
    fig = go.Figure()
    for sym in SYMBOLS:
        s = recent[recent["symbol"] == sym]
        fig.add_trace(go.Bar(y=s["contract"], x=(s["expiry"] - s["first_seen"]).dt.days * 86400000, base=s["first_seen"],
                             orientation="h", name=sym, marker=dict(color=COLORS[sym], line=dict(width=0)), opacity=.85,
                             customdata=s[["roll_out", "peak_oi"]],
                             hovertemplate="%{y}<br>roll-out %{customdata[0]|%d %b %Y}<br>peak OI %{customdata[1]:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=recent["roll_out"], y=recent["contract"], mode="markers", name="Roll-out",
                             marker=dict(symbol="line-ns", size=16, line=dict(width=2.5, color=DOWN))))
    fig.add_vline(x=last_day, line_dash="dot", line_color=MUTED)
    fig.update_xaxes(type="date")
    fig.update_yaxes(autorange="reversed", categoryorder="array", categoryarray=recent["contract"].tolist())
    fig.update_layout(barmode="overlay", hovermode="closest", bargap=.35)
    ui.chart(fig, max(420, 24 * len(recent)))
    up = cal[cal["expiry"] >= last_day].sort_values("expiry").head(10)
    st.dataframe(up[["contract", "symbol", "expiry", "roll_out", "peak_oi"]], hide_index=True, width="stretch",
                 column_config={"expiry": st.column_config.DateColumn("Expiry", format="DD MMM YYYY"),
                                "roll_out": st.column_config.DateColumn("GoldLens rolls out", format="DD MMM YYYY"),
                                "peak_oi": st.column_config.NumberColumn("Peak open interest", format="%,.0f")})
    st.caption("Specs per the PS: " + "; ".join(f"{s} expires {SPECS[s].expiry_window}" for s in SYMBOLS) + ".")

# ================================================================ Data quality
with tabs[8]:
    dq = data_quality(ws.df)
    ui.section("Data-quality guards", f"{dq['trading_days']} trading days from MCX's public Bhavcopy, "
               f"{dq['first_day']} to {dq['last_day']}. Every guard below ran on every file.", "Trust the inputs")
    ui.checklist([
        ("Date check", "Requests use DD/MM/YYYY, responses MM/DD/YYYY. A file with any other date is rejected whole.",
         f"{dq['rejected_date_mismatch']} rejected"),
        ("Holiday detection", "Empty files are recorded as holidays, never filled with stale data.", f"{dq['holidays']} holidays"),
        ("Contracts tracked by expiry", "Expiries like 04SEP2026 are parsed; no stitched near-month series.",
         f"{dq['contracts']} contracts"),
        ("Stale prices quarantined", "Zero-volume rows repeat yesterday's close: used to mark positions, never for signals.",
         f"{dq['stale_rows']:,} rows"),
        ("Symbol cleanup", "MCX pads symbols with spaces; trimmed before matching specs.", "4 symbols"),
        ("Curve sanity", "A daily fit error that jumps flags a bad print before it reaches the scanner.",
         f"{ws.curves['fit_rmse_bps'].median():.1f} bps median"),
    ])
    fig = go.Figure(go.Scatter(x=ws.curves.index, y=ws.curves["fit_rmse_bps"].rolling(5, min_periods=1).median(),
                               line=dict(color="#A78BFA", width=1.4), fill="tozeroy", fillcolor="rgba(167,139,250,.08)"))
    fig.update_layout(title="Daily curve-fit error, bps (5-day median)", showlegend=False)
    ui.chart(fig, 260)
    st.caption(f"Latest file, {dq['last_day']}: every gold futures row as received, normalised.")
    st.dataframe(ws.df[ws.df["date"] == last_day][["contract", "close", "px10", "volume", "oi", "traded", "dte"]],
                 hide_index=True, width="stretch", column_config={
                     "px10": st.column_config.NumberColumn("₹/10 g 999", format="%,.0f"),
                     "close": st.column_config.NumberColumn("Quoted", format="%,.0f")})
    st.download_button("Download full normalised panel (CSV)", ws.df.to_csv(index=False), "goldlens_panel.csv",
                       icon=":material/download:")

# ================================================================ Ask
with tabs[9]:
    ui.section("Ask GoldLens", "Answers use only today's computed fact sheet. If the numbers can't answer it, "
               "GoldLens says so.", "AI analyst")
    if not ai.has_key():
        st.info("The Q&A needs an AI key: add ANTHROPIC_API_KEY, XAI_API_KEY or OPENROUTER_API_KEY to .env.",
                icon=":material/key:")
    history = st.session_state.setdefault("chat", [])
    suggestion = st.pills("Try", ["Why do GOLDGUINEA and GOLDPETAL trade rich?", "Is any alert worth the costs today?",
                                  "What does the honest backtest prove?", "Explain carry in simple words"],
                          label_visibility="collapsed", key="ask_pills", disabled=not ai.has_key())
    for role, text in history:
        st.chat_message(role, avatar="🪙" if role == "assistant" else None).markdown(text)
    typed = st.chat_input("Ask about today's gold market…", disabled=not ai.has_key())
    q = typed or (suggestion if suggestion and st.session_state.get("last_pill") != suggestion else None)
    if suggestion:
        st.session_state["last_pill"] = suggestion
    if q:
        st.chat_message("user").markdown(q)
        with st.chat_message("assistant", avatar="🪙"):
            answer = st.write_stream(ai.stream("ask", facts, language, question=q))
        history += [("user", q), ("assistant", answer)]
    with st.expander("Fact sheet sent to the model", icon=":material/data_object:"):
        st.json(facts)
