"""HTML for every page of the GoldLens website. The server sends these whole or as htmx fragments."""
from __future__ import annotations

import datetime
import html
import json
import os

import numpy as np
import pandas as pd

from .. import ai, charts, live, notify, telegram, tipcheck, ui
from ..analytics import rolldown_decomposition
from ..backtest import attribution
from ..config import LEG_GRAMS, SPECS, SYMBOLS
from ..pipeline import data_quality
from ..ui import BLUE, DOWN, MUTED, UP, inr
from . import state
from .state import Params

esc = ui.esc
NAV = [("overview", "space_dashboard", "Overview"), ("live", "sensors", "Live"), ("alerts", "notifications_active", "Alerts"),
       ("scanner", "radar", "Scanner"), ("curve", "show_chart", "Curve & carry"), ("backtest", "science", "Backtest"),
       ("tips", "fact_check", "Tip Checker"), ("calendar", "calendar_month", "Calendar"),
       ("data", "verified", "Data quality"), ("ask", "forum", "Ask GoldLens")]
PAGES = {k for k, _, _ in NAV}
LADDER_NOTES = {"Naive": "1 lot vs 1 lot, stitched series, same-day fill, no costs",
                "+ gram-matched sizing": "a spread, not a gold bet",
                "+ fill next day": "can't trade at the price that made the signal",
                "+ past-only z-score": "no peeking at the future mean",
                "+ real contracts & carry": "no fake jumps at expiry",
                "+ costs": "brokerage, fees, CTT, stamp, GST, slippage",
                "+ liquidity filter (honest)": "no trading on stale prices"}


# ---------------------------------------------------------------- small helpers
def icon(name: str) -> str:
    return f'<span class="ms" aria-hidden="true">{name}</span>'


def plot(fig) -> str:
    data = fig.to_json().replace("</", "<\\/")
    h = fig.layout.height or 360
    return f'<div class="plot" style="min-height:{h}px"><script type="application/json">{data}</script></div>'


def info(text: str, kind: str = "info", ico: str = "info") -> str:
    return f'<div class="note {kind}">{icon(ico)}<div>{text}</div></div>'


def md(text: str) -> str:
    """The AI's light Markdown as HTML (escaped first)."""
    return "<p>" + telegram.md_to_html(text.strip()).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def table(rows: list[dict], cols: list[tuple[str, str, callable]]) -> str:
    head = "".join(f"<th>{esc(label)}</th>" for _, label, _ in cols)
    body = "".join("<tr>" + "".join(f"<td>{fmt(r.get(k)) if fmt else esc(r.get(k, ''))}</td>" for k, _, fmt in cols)
                   + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def fnum(d=0):
    return lambda v: "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.{d}f}"


def fdate(v):
    return "" if v is None or pd.isna(v) else pd.Timestamp(v).strftime("%d %b %Y")


def checked(b: bool) -> str:
    return " checked" if b else ""


# ---------------------------------------------------------------- shell
def shell(p: Params, active: str, body: str, local: bool) -> str:
    ws = state.workspace(p.roll_bdays)
    rows, honest, facts = state.today(p)
    m = facts["market"]
    last_day = ws.df["date"].max()
    w = state.watch(p.roll_bdays)
    n_alert = sum(a["status"] == "ALERT" for a in rows)
    n_flag = sum(a["status"] == "Flagged, below cost" for a in rows)
    nxt = ws.calendar[ws.calendar["expiry"] >= last_day].sort_values("expiry").iloc[0]
    tick = ui.ticker_html([{"sym": r["symbol"], "sub": r["contract"], "px": f"₹{r['px10']:,.0f}", "chg": r["chg"]} for r in w] + [
        {"sym": "SPOT", "sub": "implied · 999", "px": f"₹{m['spot_implied']:,.0f}", "chg": m["spot_change_30d_pct"]},
        {"sym": "CARRY", "sub": "annualised", "px": f"{m['carry_pct']:.2f}%"},
        {"sym": "SIGNALS", "sub": "today", "px": f"{n_alert} alert · {n_flag} flagged"},
        {"sym": "NEXT EXPIRY", "sub": nxt["contract"], "px": f"{(nxt['expiry'] - last_day).days} days"},
        {"sym": "HONEST P&L", "sub": "after costs", "px": inr(honest["net_pnl"], signed=True)}])
    chain = ai.chain()
    ai_label = (ai.last_used or " → ".join(ai.LABELS[x] for x in chain)) if chain else "template"
    live_on = bool(live.get_token())
    nav = "".join(
        f'<a href="/app/{k}" class="nav-i{" on" if k == active else ""}" data-page="{k}" hx-get="/app/{k}" '
        f'hx-target="#main" hx-push-url="true" hx-swap="innerHTML">{icon(ic)}<span>{label}</span></a>'
        for k, ic, label in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GoldLens · {esc(dict((k, l) for k, _, l in NAV).get(active, 'App'))}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'><circle cx='21' cy='21' r='15' fill='%23E0B04A'/><path d='M32 32l9 9' stroke='%23E0B04A' stroke-width='5' stroke-linecap='round'/></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,300..500,0..1,0&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/app/static/components.css"><link rel="stylesheet" href="/app/static/app.css">
</head><body class="app" hx-headers='{{"X-GoldLens": "1"}}'>
<aside class="side">
  <a class="brand" href="/">{ui.LOGO_IMG}<span>GoldLens</span></a>
  <nav class="nav">{nav}</nav>
  <button class="nav-i settings-btn" type="button" data-open="settings">{icon("tune")}<span>Settings</span></button>
  <a class="nav-i" href="/">{icon("home")}<span>About GoldLens</span></a>
</aside>
<div class="shell">
  <header class="topbar">
    <div class="pills">
      {'<span class="gl-pill"><span class="dot live"></span><b>LIVE</b> Upstox</span>' if live_on else '<span class="gl-pill"><span class="dot blue"></span><b>EOD</b> MCX Bhavcopy</span>'}
      <span class="gl-pill">Settlement <b>{last_day:%d %b %Y}</b></span>
      <span class="gl-pill">History <b>{ws.df['date'].min():%b %Y} – {last_day:%b %Y}</b></span>
      <span class="gl-pill"><span class="dot {'gold' if chain else ''}"></span>AI <b>{esc(ai_label)}</b></span>
      <span class="gl-pill">Language <b>{esc(p.language)}</b></span>
    </div>
    <div class="loading htmx-indicator" id="page-loading"><span class="spin"></span>Loading…</div>
  </header>
  {tick}
  <main id="main" hx-indicator="#page-loading">{body}</main>
  <footer class="appfoot">Statistical analysis for education, not investment advice · Data: MCX daily Bhavcopy</footer>
</div>
{settings_drawer(p)}
<script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js"></script>
<script src="/app/static/plotly.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script src="/app/static/app.js"></script>
</body></html>"""


def settings_drawer(p: Params) -> str:
    def rng(name, label, lo, hi, step, unit=""):
        v = getattr(p, name)
        return (f'<label class="fld"><span>{label} <b data-out="{name}">{v:g}{unit}</b></span>'
                f'<input type="range" name="{name}" min="{lo}" max="{hi}" step="{step}" value="{v}"></label>')
    return f"""<div class="drawer" id="settings" aria-hidden="true"><div class="drawer-bg" data-close></div>
<form class="drawer-panel" hx-post="/app/settings" hx-swap="none">
  <div class="drawer-hd"><b>Settings</b><button type="button" class="icon-btn" data-close>{icon("close")}</button></div>
  <div class="grp"><h5>AI analyst language</h5>
    <div class="seg"><label><input type="radio" name="language" value="English"{checked(p.language == 'English')}><span>English</span></label>
    <label><input type="radio" name="language" value="Hindi"{checked(p.language == 'Hindi')}><span>Hindi</span></label></div></div>
  <div class="grp"><h5>Strategy</h5>
    {rng("window", "Z-score lookback", 20, 120, 5, " d")}{rng("entry_z", "Entry |z|", 1.5, 3.5, 0.1)}
    {rng("exit_z", "Exit |z|", 0, 1.5, 0.1)}{rng("max_hold", "Max holding days", 5, 60, 5)}
    {rng("min_volume", "Min lots per leg", 0, 500, 10)}{rng("roll_bdays", "Roll out before expiry", 2, 10, 1, " bd")}</div>
  <div class="grp"><h5>Costs</h5>
    {rng("slippage", "Slippage, ticks per fill", 0, 6, 0.5)}{rng("brokerage", "Brokerage per order ₹", 0, 100, 5)}
    <label class="chk"><input type="checkbox" name="fees_on" value="on"{checked(p.fees_on)}><span>Exchange fees, CTT, stamp duty, GST</span></label></div>
  <p class="foot">Parameters are fixed up front, not tuned on the results.</p>
  <button class="btn primary" type="submit">{icon("check")}Apply</button>
</form></div>"""


# ---------------------------------------------------------------- Overview
def overview(p: Params) -> str:
    ws = state.workspace(p.roll_bdays)
    rows, honest, facts = state.today(p)
    m = facts["market"]
    hd = state.custom(p)[0]["total"]
    hres = state.custom(p)[1]
    sig = pd.concat({k: r.signal["z"].abs() >= p.entry_z for k, r in hres.items()}, axis=1).sum(axis=1).tail(120)
    n_alert = sum(a["status"] == "ALERT" for a in rows)
    n_flag = sum(a["status"] == "Flagged, below cost" for a in rows)
    chg = m["spot_change_30d_pct"]
    k = ui.kpis_html([
        {"label": "Implied spot · ₹/10 g 999", "value": f"₹{m['spot_implied']:,.0f}", "accent": True,
         "sub": f'<span class="{ui.tone(chg)}">{ui.arrow(chg)} {chg:+.2f}%</span> in 30 days' if chg is not None else "",
         "spark": ws.curves["spot_implied"].tail(120).tolist()},
        {"label": "Futures carry · annualised", "value": f"{m['carry_pct']:.2f}%", "color": BLUE,
         "sub": "what the market charges to hold gold forward", "spark": (ws.curves["carry"] * 100).tail(120).tolist()},
        {"label": "Signals today", "value": f"{n_alert}<span class='dim'> / {len(rows)}</span>",
         "sub": f"{n_flag} flagged but below cost · quiet by design", "spark": sig.tolist(), "color": "#A78BFA"},
        {"label": "Honest backtest · net", "value": f'<span class="{ui.tone(honest["net_pnl"])}">{inr(honest["net_pnl"], signed=True)}</span>',
         "sub": f"{honest['trades']} trades · Sharpe {ui.num(honest['sharpe'])} · after {inr(honest['costs'])} costs",
         "spark": hd.cumsum().tolist(), "color": UP if honest["net_pnl"] >= 0 else DOWN}])
    mw = ui.market_watch_html(state.watch(p.roll_bdays), f"Market watch · active contracts · {pd.Timestamp(facts['as_of']):%d %b %Y}")
    cached = ai.cached("brief", facts, p.language)
    brief_body = (md(cached) + f'<p class="foot">Cached · {esc(p.language)}</p>') if cached else (
        f'<button class="btn primary wide" hx-post="/api/brief" hx-target="#brief-out" hx-indicator="#brief-spin">'
        f'{icon("auto_awesome")}Write today\'s brief</button>'
        f'<div class="htmx-indicator inline-spin" id="brief-spin"><span class="spin"></span>Writing… free AI models can take ~30 s</div>')
    brief = (f'<div class="gl-brief"><div class="hd"><span class="ttl">✦ AI daily brief</span>'
             f'<span class="by">{"Grounded in today&#39;s computed numbers" if ai.has_key() else "Template mode: no AI key in .env"}</span></div>'
             f'<div id="brief-out">{brief_body}</div></div>')
    return (ui.section_html("Overview", f"Four MCX gold futures on one scale. Settlement {pd.Timestamp(facts['as_of']):%d %b %Y}.", "Today")
            + k + f'<div class="cols-53"><div>{mw}</div><div>{brief}</div></div>'
            + ui.section_html("Same gold. Four contracts. Four prices.",
                              "Flip the switch: GoldLens converts every price to ₹ per 10 g of 999 gold, and four unrelated-looking "
                              "lines collapse into one. The small gaps left over are the signal.", "The core idea")
            + '<div class="seg big" hx-target="#norm" hx-swap="innerHTML">'
              '<button hx-get="/app/frag/normalise?mode=close">As quoted on MCX</button>'
              '<button class="on" hx-get="/app/frag/normalise?mode=px10">Normalised by GoldLens</button></div>'
            + f'<div id="norm">{plot(charts.normalise(ws, "px10"))}</div>'
            + '<p class="foot">Normalisation: price × (10 / quoted grams) × (999 / purity). GOLDGUINEA is quoted per 8 g, '
              'GOLDPETAL per 1 g, GOLDM at 995 purity.</p>')


def frag_normalise(p: Params, mode: str) -> str:
    return plot(charts.normalise(state.workspace(p.roll_bdays), "close" if mode == "close" else "px10"))


def api_brief(p: Params) -> str:
    _, _, facts = state.today(p)
    text = ai.complete("brief", facts, p.language)
    by = ai.last_used if "Template brief" not in text else "template"
    return md(text) + f'<p class="foot">Written by {esc(by or "template")} · {esc(p.language)}</p>'


# ---------------------------------------------------------------- Scanner
def scanner(p: Params, pair: str | None = None) -> str:
    ws = state.workspace(p.roll_bdays)
    rows, _, facts = state.today(p)
    names = [f"{a}/{b}" for a, b in ws.pairs]
    pick = pair if pair in names else (rows[0]["pair"] if rows else names[0])
    pills = "".join(f'<button class="{"on" if n == pick else ""}" hx-get="/app/frag/pair?pair={n}">{n}</button>' for n in names)
    return (ui.section_html("Relative-value scanner",
                            f"An alert needs |z| ≥ {p.entry_z:g}, both legs traded in size, and an expected reversion worth at least "
                            f"1.5× round-trip costs on a {LEG_GRAMS:.0f} g pair. The gold tick on each meter is that hurdle.",
                            f"Settlement {pd.Timestamp(facts['as_of']):%d %b %Y}")
            + ui.scanner_cards_html(rows, p.entry_z)
            + ui.section_html("Pair inspector", "Carry-adjusted spread with its rolling mean, entry band, and every honest-backtest trade.")
            + f'<div class="seg wrap" hx-target="#pair" hx-swap="innerHTML">{pills}</div><div id="pair">{frag_pair(p, pick)}</div>'
            + ui.section_html("Who trades rich?", "Premium of each contract over GOLDM after units, purity and carry are removed "
                              "(5-day median). Retail demand pushed the small contracts 200–450 bps rich in early 2026.")
            + plot(charts.premiums(ws.curves)))


def frag_pair(p: Params, pair: str) -> str:
    ws = state.workspace(p.roll_bdays)
    key = tuple(pair.split("/")) if pair else None
    if key not in ws.pairs:
        key = next(iter(ws.pairs))
    res = state.custom(p)[1][key]
    pm = res.metrics
    k = ui.kpis_html([
        {"label": "Net P&L · honest", "value": f'<span class="{ui.tone(pm["net_pnl"])}">{inr(pm["net_pnl"], signed=True)}</span>',
         "sub": f"{pm['ann_return_pct']:+.2f}% a year on one-leg notional", "spark": res.daily["net"].cumsum().tolist(),
         "color": UP if pm["net_pnl"] >= 0 else DOWN},
        {"label": "Gross before costs", "value": inr(pm["gross_pnl"], signed=True), "sub": "spread P&L on held contracts"},
        {"label": "Costs paid", "value": inr(pm["costs"]), "sub": "fees, taxes, slippage, rolls"},
        {"label": "Trades · win rate", "value": f"{pm['trades']} · {pm['win_rate'] * 100:.0f}%",
         "sub": f"Sharpe {ui.num(pm['sharpe'])} · max DD {inr(pm['max_drawdown'])}"}])
    name = "/".join(key)
    return (plot(charts.pair(res, p.window, p.entry_z, *key)) + k
            + f'<div class="row-btns"><button class="btn" hx-post="/api/explain?pair={name}" hx-target="#explain" '
              f'hx-indicator="#explain-spin">{icon("auto_awesome")}Explain {name} with the AI analyst</button>'
              f'<span class="htmx-indicator inline-spin" id="explain-spin"><span class="spin"></span>Thinking…</span></div>'
              f'<div id="explain"></div>')


def api_explain(p: Params, pair: str) -> str:
    ws = state.workspace(p.roll_bdays)
    rows, _, _ = state.today(p)
    sel = next((a for a in rows if a["pair"] == pair), None)
    if sel is None:
        return info("Unknown pair.", "warn")
    pm = state.custom(p)[1][tuple(pair.split("/"))].metrics
    return f'<div class="gl-panel answer">{md(ai.complete("alert", {**sel, "pair_backtest": pm}, p.language))}</div>'


# ---------------------------------------------------------------- Curve & carry
def curve(p: Params) -> str:
    ws = state.workspace(p.roll_bdays)
    n = len(ws.curves)
    return (ui.section_html("Term structure", "Every traded contract on one fair curve: ln(price) = ln(spot) + carry × "
                            "time-to-expiry + a premium per contract type.", "Curve & carry")
            + f'<label class="slider-row"><span>Curve date</span><input type="range" name="d" min="0" max="{n - 1}" value="{n - 1}" '
              f'hx-get="/app/frag/curve" hx-target="#curve" hx-trigger="change"><output data-dates="1"></output></label>'
            + f'<div id="curve">{frag_curve(p, n - 1)}</div>'
            + '<div class="cols-11"><div>' + plot(charts.carry(ws.curves)) + '</div><div>'
            + f'<form class="rd-form" hx-get="/app/frag/rolldown" hx-target="#rolldown" hx-trigger="change">'
              f'<label class="slider-row"><span>Period start</span><input type="range" name="s" min="0" max="{n - 2}" value="{max(0, n - 22)}"></label>'
              f'<label class="slider-row"><span>Days to expiry at start</span><input type="range" name="tau" min="15" max="180" step="5" value="60"><output></output></label>'
              f'</form><div id="rolldown">{frag_rolldown(p, max(0, n - 22), 60)}</div></div></div>')


def frag_curve(p: Params, idx: int) -> str:
    ws = state.workspace(p.roll_bdays)
    dates = ws.curves.index
    idx = int(min(max(idx, 0), len(dates) - 1))
    day = dates[idx]
    c = ws.curves.loc[day]
    k = ui.kpis_html([
        {"label": f"Implied carry · {day:%d %b %Y}", "value": f"{c['carry'] * 100:.2f}%", "sub": "per year", "color": BLUE,
         "spark": (ws.curves["carry"].loc[:day].tail(90) * 100).tolist()},
        {"label": "Implied spot · ₹/10 g 999", "value": f"₹{c['spot_implied']:,.0f}", "accent": True,
         "spark": ws.curves["spot_implied"].loc[:day].tail(90).tolist()},
        {"label": "Curve fit error", "value": f"{c['fit_rmse_bps']:.1f} bps", "sub": "volume-weighted RMSE"},
        {"label": "Contracts on the curve", "value": f"{int(c['n'])}", "sub": "traded that day"}])
    return k + plot(charts.term_structure(ws, day))


def frag_rolldown(p: Params, start_idx: int, tau_days: int) -> str:
    ws = state.workspace(p.roll_bdays)
    dates = ws.curves.index
    start_idx = int(min(max(start_idx, 0), len(dates) - 2))
    dec = rolldown_decomposition(ws.curves, int(tau_days) / 365, dates[start_idx], dates[-1])
    if not dec:
        return info("Pick an earlier start date.")
    return (plot(charts.rolldown(dec))
            + f'<p class="foot">From {dates[start_idx]:%d %b %Y} to {dates[-1]:%d %b %Y} ({dec["days"]} days), a contract that started '
              f'with {int(tau_days)} days left moved {dec["total_bps"]:+.0f} bps: {dec["rolldown_bps"]:+.0f} bps just from time passing '
              '(futures converge to spot); the rest from gold itself and the carry rate.</p>')


# ---------------------------------------------------------------- Backtest
FLAG_LABELS = [("gram_matched", "Gram-matched"), ("next_day_fill", "Fill T+1"), ("rolling_stats", "Past-only stats"),
               ("true_contracts", "Real contracts"), ("apply_costs", "Costs"), ("liquidity_filter", "Liquidity filter")]


def backtest(p: Params) -> str:
    lad = state.ladder(p)
    ws = state.workspace(p.roll_bdays)
    toggles = "".join(f'<label class="tgl"><input type="checkbox" name="{k}" value="1" checked><span></span>{label}</label>'
                      for k, label in FLAG_LABELS)
    return (ui.section_html("Where does a backtest's edge come from?",
                            f"The same strategy replayed with one common flaw removed at each step, net P&L over all {len(ws.pairs)} "
                            f"pairs at {LEG_GRAMS:.0f} g per leg. Watch the edge evaporate.", "The honesty test")
            + ui.funnel_html([(n, LADDER_NOTES.get(n, ""), t["net_pnl"]) for n, _, t in lad])
            + plot(charts.ladder_equity(lad))
            + ui.section_html("Run your own", "Switch any fix off to see how much fake edge it creates.")
            + f'<form class="toggles" hx-get="/app/frag/custom" hx-target="#custom" hx-trigger="change">'
              f'<input type="hidden" name="_submitted" value="1">{toggles}</form>'
            + f'<div id="custom">{frag_custom(p, ())}</div>')


def flags_from(query: dict) -> tuple:
    """Unchecked boxes are absent from the form, so each missing flag means 'off'."""
    if not query.get("_submitted"):
        return ()
    return tuple((k, k in query) for k, _ in FLAG_LABELS)


def frag_custom(p: Params, flags: tuple) -> str:
    ws = state.workspace(p.roll_bdays)
    daily, results, tot = state.custom(p, flags)
    lad = state.ladder(p)
    k = ui.kpis_html([
        {"label": "Net P&L", "value": f'<span class="{ui.tone(tot["net_pnl"])}">{inr(tot["net_pnl"], signed=True)}</span>',
         "spark": daily["total"].cumsum().tolist(), "color": UP if tot["net_pnl"] >= 0 else DOWN, "sub": f"{tot['trades']} trades"},
        {"label": "Gross before costs", "value": inr(tot["gross_pnl"], signed=True), "sub": "what most backtests report"},
        {"label": "Costs", "value": inr(tot["costs"]), "sub": "every fill, every roll"},
        {"label": "Sharpe · max drawdown", "value": ui.num(tot["sharpe"]), "sub": f"max DD {inr(tot['max_drawdown'])}"}])
    per = sorted(({"pair": f"{a}/{b}", **r.metrics} for (a, b), r in results.items()), key=lambda r: -r["net_pnl"])
    tbl = table(per, [("pair", "Pair", None), ("net_pnl", "Net ₹", fnum()), ("gross_pnl", "Gross ₹", fnum()),
                      ("costs", "Costs ₹", fnum()), ("trades", "Trades", fnum()),
                      ("win_rate", "Win rate", lambda v: f'<span class="wr"><i style="width:{v * 100:.0f}%"></i></span>{v * 100:.0f}%'),
                      ("sharpe", "Sharpe", ui.num), ("max_drawdown", "Max DD ₹", fnum()),
                      ("ann_return_pct", "Return / yr", lambda v: f"{v:+.2f}%")])
    gold = ws.front.xs("GOLDM", level="symbol")["px10"]
    a_c, a_n = attribution(daily["total"], gold), attribution(lad[0][1], gold)
    scale = max(abs(a_n["beta_grams"]), abs(a_c["beta_grams"]), 1)
    vs = ui.versus_html(
        {"label": "Naive backtest", "value": f'{a_n["beta_grams"]:+.0f} g of gold',
         "sub": f"R² vs gold {a_n['r2']:.2f}: its 'edge' is mostly a bet on gold", "pct": abs(a_n["beta_grams"]) / scale * 100, "color": DOWN},
        {"label": "This run", "value": f'{a_c["beta_grams"]:+.0f} g of gold',
         "sub": f"R² vs gold {a_c['r2']:.2f}: P&L comes from the spread, not gold's direction",
         "pct": abs(a_c["beta_grams"]) / scale * 100, "color": UP})
    q = "&".join(f"{k}={'1' if v else '0'}" for k, v in flags) if flags else ""
    return (k + tbl + ui.section_html("Honest attribution: strategy, or just gold?",
                                      "Daily P&L regressed on the rupee move of holding gold outright (HAC errors).") + vs
            + f'<p class="row-btns"><a class="btn" href="/api/trades.csv?{q}">{icon("download")}Download this run\'s trades (CSV)</a></p>')


# ---------------------------------------------------------------- Tip Checker
def tips(p: Params) -> str:
    ex = "".join(f'<button type="button" class="chip-btn" data-fill="#tip-text" data-text="{esc(t)}">{esc(lbl)}</button>'
                 for lbl, t in zip(["“PETAL 1% cheaper, 40% guaranteed”", "“Guinea premium, 5% monthly”", "“2-sigma TEN vs GUINEA”"],
                                   tipcheck.EXAMPLES))
    ws = state.workspace(p.roll_bdays)
    return (ui.section_html("Tip Checker", "Paste any tip about MCX gold contracts, from Telegram, Instagram or a friend. "
                            "GoldLens turns it into a precise rule, tests it the way tipsters usually do, then tests it honestly on "
                            f"{ws.df['date'].nunique()} trading days of real MCX data.", "A lie detector for trading tips")
            + f'<div class="chips">{ex}</div>'
            + '<form hx-post="/api/tip" hx-target="#tip-out" hx-indicator="#tip-spin" class="tip-form">'
              '<textarea id="tip-text" name="tip" rows="3" placeholder="e.g. Buy GOLDPETAL when it\'s 1% cheaper than GOLDM, sell when it '
              'comes back. 40% a year guaranteed!"></textarea>'
              f'<div class="row-btns"><button class="btn primary" type="submit">{icon("fact_check")}Check this tip</button>'
              '<span class="htmx-indicator inline-spin" id="tip-spin"><span class="spin"></span>Reading the tip…</span></div></form>'
              '<div id="tip-out"></div>')


SIDE_LBL = {"long_a": "Buy A when cheap", "short_a": "Sell A when rich", "both": "Both directions"}


def tip_editor(rule: tipcheck.Rule) -> str:
    def opt(val, cur, label=None):
        return f'<option value="{val}"{" selected" if val == cur else ""}>{esc(label or val)}</option>'
    unit = "bps (100 = 1%)" if rule.mode == "level" else "σ"
    flags = esc(json.dumps(rule.red_flags))
    return f"""<form class="tip-editor gl-panel" hx-post="/api/tip/eval" hx-target="#tip-verdict" hx-trigger="change">
<input type="hidden" name="source" value="{esc(rule.source)}"><input type="hidden" name="flags" value="{flags}">
<div class="ed-grid">
<label>Leg A (traded on the signal)<select name="a">{''.join(opt(s, rule.buy_leg) for s in SYMBOLS)}</select></label>
<label>Leg B (the comparison)<select name="b">{''.join(opt(s, rule.other_leg) for s in SYMBOLS)}</select></label>
<label>Direction<select name="side">{''.join(opt(k, rule.side, v) for k, v in SIDE_LBL.items())}</select></label>
<label>Threshold in<select name="mode">{opt("level", rule.mode, "bps gap")}{opt("z", rule.mode, "z-score")}</select></label>
<label>Enter when gap passes, {unit}<input type="number" name="entry" step="any" min="0.1" value="{rule.entry:g}"></label>
<label>Exit when gap is back to, {unit}<input type="number" name="exit" step="any" min="0" value="{rule.exit:g}"></label>
<label>Max holding days<input type="number" name="hold" min="1" max="120" value="{rule.max_hold}"></label>
<label>Claimed return, % a year<input type="number" name="claim" min="0" step="any" value="{rule.claimed_annual_pct or 0:g}"></label>
</div></form>"""


def api_tip(p: Params, text: str) -> str:
    if not (text or "").strip():
        return info("Paste a tip first.", "warn")
    rule = tipcheck.parse_tip(text)
    if rule is None or "out of scope" in rule.notes:
        return info("GoldLens can only check tips about the price gap between MCX gold contracts (GOLDM, GOLDTEN, GOLDGUINEA, "
                    "GOLDPETAL). This one is out of scope, so it isn't guessed at.", "warn", "block")
    notes = "".join(f'<p class="foot">Assumption: {esc(n)}</p>' for n in rule.notes)
    return tip_editor(rule) + notes + f'<div id="tip-verdict">{tip_verdict(p, rule)}</div>'


def rule_from_form(f: dict) -> tipcheck.Rule:
    def fl(k, d):
        try:
            return float(f.get(k, d))
        except (TypeError, ValueError):
            return d
    a = f.get("a") if f.get("a") in SYMBOLS else "GOLDPETAL"
    b = f.get("b") if f.get("b") in SYMBOLS and f.get("b") != a else next(s for s in SYMBOLS if s != a)
    entry = max(fl("entry", 100.0), 0.1)
    try:
        flags = json.loads(f.get("flags") or "[]")
    except ValueError:
        flags = []
    return tipcheck.Rule(a, b, f.get("side") if f.get("side") in SIDE_LBL else "long_a",
                         "z" if f.get("mode") == "z" else "level", entry, min(max(fl("exit", 0.0), 0.0), entry * 0.95),
                         int(min(max(fl("hold", 20), 1), 120)), fl("claim", 0.0) or None, str(f.get("source", "you"))[:60],
                         red_flags=[str(x)[:200] for x in flags][:5])


def tip_verdict(p: Params, rule: tipcheck.Rule) -> str:
    ev = tipcheck.evaluate(rule, state.workspace(p.roll_bdays), p.cfg())
    kind, title, detail = ev["verdict"]
    nv, hn = ev["naive"], ev["honest"]
    claim = rule.claimed_annual_pct
    left = ui.breakdown_html(ev["breakdown"]) if ev["breakdown"] else \
        '<div class="gl-panel"><h4>Where the paper profit went</h4><p class="foot">No step removed profit.</p></div>'
    steps = ui.funnel_html([(s["name"], tipcheck.REASONS.get(s["name"], "the tip exactly as stated"), s["net"]) for s in ev["steps"]])
    return (ui.rulebox_html(rule.describe(), rule.source) + ui.verdict_html(kind, title, detail, rule.red_flags)
            + ui.kpis_html([
                {"label": "Claimed", "value": f"{claim:.0f}% / yr" if claim else "not stated", "sub": "what the tip promises"},
                {"label": "Tipster-style test", "value": f'<span class="{ui.tone(nv["ann_pct"])}">{nv["ann_pct"]:+.1f}% / yr</span>',
                 "sub": f"{nv['trades']} trades · no costs, perfect fills, stitched prices",
                 "spark": nv["result"].daily["net"].cumsum().tolist(), "color": MUTED},
                {"label": "Honest test", "value": f'<span class="{ui.tone(hn["ann_pct"])}">{hn["ann_pct"]:+.1f}% / yr</span>',
                 "sub": f"{hn['trades']} trades · real contracts, costs, next-day fills",
                 "spark": hn["result"].daily["net"].cumsum().tolist(), "color": UP if hn["ann_pct"] > 0 else DOWN, "accent": True},
                {"label": "Hidden gold bet", "value": f'{ev["attr_naive"]["beta_grams"]:+.0f} g → {ev["attr_honest"]["beta_grams"]:+.0f} g',
                 "sub": "gold exposure: tipster-style vs honest"}])
            + f'<div class="cols-11"><div>{left}</div><div>{plot(charts.tip_equity(ev))}</div></div>'
            + f'<details class="gl-panel"><summary>Every step of the honesty test</summary>{steps}</details>'
            + f'<p class="foot">Tested on {ev["first"]:%d %b %Y} – {ev["last"]:%d %b %Y}, {LEG_GRAMS:.0f} g per leg in the honest test. '
              'Returns are on the larger leg\'s notional, unlevered. Educational tool, not investment advice.</p>')


# ---------------------------------------------------------------- Alerts (Telegram)
def alerts(p: Params, local: bool, flash: tuple | None = None) -> str:
    return (ui.section_html("Morning briefing on Telegram",
                            "One message every morning: the gold price, today's signals, premiums vs GOLDM, upcoming expiries and a short "
                            "AI take. Connect your own Telegram bot in under a minute.", "Alerts")
            + f'<div id="alerts-body">{alerts_body(p, local, flash)}</div>')


def alerts_body(p: Params, local: bool, flash: tuple | None = None, when: str = "08:30") -> str:
    ws = state.workspace(p.roll_bdays)
    rows, _, facts = state.today(p)
    token, chat = telegram.get_config()
    lang = os.environ.get("TELEGRAM_LANGUAGE", "English")
    fl = info(esc(flash[1]), "ok" if flash[0] else "warn", "check_circle" if flash[0] else "info") if flash else ""
    if telegram.is_configured():
        try:
            me = telegram.get_me(token)
            name = f"@{me.get('username')}"
        except telegram.TelegramError as e:
            me, name = {}, f"bot (error: {e})"
        conn = (f'<div class="gl-panel"><h4>Connection</h4><div class="conn"><span class="dot live"></span>'
                f'<b>Connected to {esc(name)}</b></div><p class="foot">Token {esc(telegram.mask(token))} · chat {esc(chat)} · '
                f'language {esc(lang)}</p><div class="row-btns">'
                f'<button class="btn primary" hx-post="/api/telegram/send" hx-target="#alerts-body" hx-indicator="#tg-spin">{icon("send")}Send today\'s message now</button>'
                f'<button class="btn" hx-post="/api/telegram/test" hx-target="#alerts-body">{icon("notifications")}Send test</button>'
                + (f'<button class="btn" hx-post="/api/telegram/disconnect" hx-target="#alerts-body" '
                   f'hx-confirm="Disconnect this bot? The token will be removed from .env.">{icon("link_off")}Disconnect</button>' if local else "")
                + '<span class="htmx-indicator inline-spin" id="tg-spin"><span class="spin"></span>Sending…</span></div></div>')
        bot_name = me.get("first_name") or "GoldLens Bot"
    else:
        steps = ('<div class="gl-panel"><h4>Connect in 4 steps</h4><ol class="steps4"><li>In Telegram, open <b>@BotFather</b> and send '
                 '<code>/newbot</code></li><li>Pick a name; BotFather replies with a <b>token</b>. Paste it below</li>'
                 '<li>Open your new bot and press <b>Start</b></li><li>Click <b>Connect</b>. GoldLens finds your chat and sends a hello</li></ol></div>')
        form = (f'<form class="tg-form" hx-post="/api/telegram/connect" hx-target="#alerts-body" hx-indicator="#tg-spin">'
                f'<label>Bot token<input type="password" name="token" placeholder="123456789:AAH…" autocomplete="off" value="{esc(token or "")}"></label>'
                f'<div class="row-btns"><button class="btn primary" type="submit">{icon("link")}Connect</button>'
                f'<span class="htmx-indicator inline-spin" id="tg-spin"><span class="spin"></span>Checking the token…</span></div>'
                f'<p class="foot">Stored only in this computer\'s .env file, never shown in full.</p></form>') if local else \
            info("Connecting a bot is only available on the computer running GoldLens.", "warn", "lock")
        conn, bot_name = steps + form, "GoldLens Bot"
    sched = (f'<div class="gl-panel"><h4>Send it every morning</h4><form class="sched" hx-post="/api/telegram/lang" '
             f'hx-target="#alerts-body" hx-trigger="change">'
             f'<label>Send time<input type="time" name="when" value="{esc(when)}" step="900"></label>'
             f'<label>Language<select name="lang"{" disabled" if not local else ""}>'
             f'<option{" selected" if lang == "English" else ""}>English</option><option{" selected" if lang == "Hindi" else ""}>Hindi</option>'
             f'</select></label></form><p class="foot">Run this once in a terminal. Windows then refreshes the MCX data and sends '
             f'the message daily (your PC needs to be on at that time):</p><pre class="code">{esc(notify.schedule_command(when))}</pre></div>')
    preview, _ = notify.build_morning(ws, rows, facts, lang, use_ai=False)
    add_ai = "" if "AI take" in preview else (
        f'<button class="btn wide" hx-post="/api/telegram/preview-ai" hx-target="#alerts-body" hx-indicator="#ai-spin" '
        f'{"disabled" if not ai.has_key() else ""}>{icon("auto_awesome")}Add the AI take to this preview</button>'
        '<span class="htmx-indicator inline-spin" id="ai-spin"><span class="spin"></span>Writing… ~30 s</span>')
    return (fl + f'<div class="cols-alerts"><div>{conn}{sched}</div><div>'
            f'{ui.phone_html(preview, bot_name, when)}{add_ai}</div></div>')


# ---------------------------------------------------------------- Calendar & Data quality
def calendar(p: Params) -> str:
    ws = state.workspace(p.roll_bdays)
    last_day = ws.df["date"].max()
    up = ws.calendar[ws.calendar["expiry"] >= last_day].sort_values("expiry").head(10).to_dict("records")
    return (ui.section_html("Contract lifecycle", f"Listing to expiry for every contract. GoldLens always exits {p.roll_bdays} business "
                            "days before expiry, ahead of the tender/delivery period (red tick), and re-enters the next contract.", "Calendar")
            + plot(charts.calendar(ws.calendar, last_day))
            + table(up, [("contract", "Contract", None), ("expiry", "Expiry", fdate), ("roll_out", "GoldLens rolls out", fdate),
                         ("peak_oi", "Peak open interest", fnum())])
            + '<p class="foot">Specs per the PS: ' + "; ".join(f"{s} expires {SPECS[s].expiry_window}" for s in SYMBOLS) + ".</p>")


def data(p: Params) -> str:
    ws = state.workspace(p.roll_bdays)
    dq = data_quality(ws.df)
    last = ws.df[ws.df["date"] == ws.df["date"].max()].to_dict("records")
    return (ui.section_html("Data-quality guards", f"{dq['trading_days']} trading days from MCX's public Bhavcopy, {dq['first_day']} to "
                            f"{dq['last_day']}. Every guard below ran on every file.", "Trust the inputs")
            + ui.checklist_html([
                ("Date check", "Requests use DD/MM/YYYY, responses MM/DD/YYYY. A file with any other date is rejected whole.",
                 f"{dq['rejected_date_mismatch']} rejected"),
                ("Holiday detection", "Empty files are recorded as holidays, never filled with stale data.", f"{dq['holidays']} holidays"),
                ("Contracts tracked by expiry", "Expiries like 04SEP2026 are parsed; no stitched near-month series.", f"{dq['contracts']} contracts"),
                ("Stale prices quarantined", "Zero-volume rows repeat yesterday's close: used to mark positions, never for signals.",
                 f"{dq['stale_rows']:,} rows"),
                ("Symbol cleanup", "MCX pads symbols with spaces; trimmed before matching specs.", "4 symbols"),
                ("Curve sanity", "A daily fit error that jumps flags a bad print before it reaches the scanner.",
                 f"{ws.curves['fit_rmse_bps'].median():.1f} bps median")])
            + plot(charts.fit_error(ws.curves))
            + f'<p class="foot">Latest file, {dq["last_day"]}: every gold futures row as received, normalised.</p>'
            + table(last, [("contract", "Contract", None), ("close", "Quoted", fnum()), ("px10", "₹/10 g 999", fnum()),
                           ("volume", "Volume", fnum()), ("oi", "Open interest", fnum()), ("traded", "Traded", lambda v: "yes" if v else "no"),
                           ("dte", "Days to expiry", fnum())])
            + f'<p class="row-btns"><a class="btn" href="/api/panel.csv">{icon("download")}Download the full normalised panel (CSV)</a></p>')


# ---------------------------------------------------------------- Ask
SUGGEST = ["Why do GOLDGUINEA and GOLDPETAL trade rich?", "Is any alert worth the costs today?",
           "What does the honest backtest prove?", "Explain carry in simple words"]


def ask(p: Params) -> str:
    _, _, facts = state.today(p)
    sug = "".join(f'<button class="chip-btn" hx-post="/api/ask" hx-vals=\'{{"q": "{esc(s)}"}}\' hx-target="#chat" '
                  f'hx-swap="beforeend" hx-indicator="#ask-spin">{esc(s)}</button>' for s in SUGGEST)
    disabled = "" if ai.has_key() else " disabled"
    return (ui.section_html("Ask GoldLens", "Answers use only today's computed fact sheet. If the numbers can't answer it, GoldLens says so.", "AI analyst")
            + ("" if ai.has_key() else info("The Q&A needs an AI key: add ANTHROPIC_API_KEY, XAI_API_KEY or OPENROUTER_API_KEY to .env.", "warn", "key"))
            + f'<div class="chips">{sug}</div><div id="chat" class="chat"></div>'
            + f'<form class="ask-form" hx-post="/api/ask" hx-target="#chat" hx-swap="beforeend" hx-indicator="#ask-spin" '
              f'data-reset="1"><input name="q" placeholder="Ask about today\'s gold market…" autocomplete="off"{disabled}>'
              f'<button class="btn primary"{disabled}>{icon("send")}</button></form>'
            + '<div class="htmx-indicator inline-spin" id="ask-spin"><span class="spin"></span>Thinking… free models can take ~30 s</div>'
            + f'<details class="gl-panel"><summary>Fact sheet sent to the model</summary><pre class="code">'
              f'{esc(json.dumps(facts, indent=1, default=str))}</pre></details>')


def api_ask(p: Params, q: str) -> str:
    q = (q or "").strip()[:500]
    if not q:
        return ""
    _, _, facts = state.today(p)
    answer = ai.complete("ask", facts, p.language, question=q)
    return (f'<div class="msg-u">{esc(q)}</div>'
            f'<div class="msg-a"><span class="av">🪙</span><div>{md(answer)}</div></div>')


# ---------------------------------------------------------------- Live
def live_page(p: Params) -> str:
    return (ui.section_html("Live scanner", "Live MCX quotes from Upstox, scored against the same past-only statistics as the daily "
                            "scanner. The cost hurdle uses the real order book: buy at the ask, sell at the bid. Refreshes every "
                            f"{live.refresh_seconds()} s.", "Real time")
            + f'<div id="live" hx-get="/app/frag/live" hx-trigger="load, every {live.refresh_seconds()}s" hx-swap="innerHTML">'
              '<div class="inline-spin"><span class="spin"></span>Fetching quotes…</div></div>')


def frag_live(p: Params) -> str:
    ws = state.workspace(p.roll_bdays)
    rows, _, facts = state.today(p)
    snap = live.snapshot(p.roll_bdays)
    q = None
    if snap.ok:
        settle = ws.df[ws.df["date"] == ws.df["date"].max()].set_index("contract")["px10"]
        q = snap.quotes.copy()
        q["vs_settle_pct"] = (q["px10"] / q["contract"].map(settle) - 1) * 100
        if q["vs_settle_pct"].abs().max() > 8:
            snap.ok = False
            snap.message = "Unit check failed: live prices differ from the last settlement by more than 8%, so they are not scored."
    if not snap.ok:
        setup = "" if live.get_token() else (
            '<div class="gl-panel"><h4>Turn on live data</h4><p class="foot">Free Upstox account → <b>Developer Apps</b> → '
            '<b>Analytics</b> tab → <b>Generate Token</b>, then add <code>UPSTOX_ANALYTICS_TOKEN=…</code> to <code>.env</code>. '
            'Read-only, valid for a year.</p></div>')
        return info(esc(snap.message), "info", "event") + ui.scanner_cards_html(rows, p.entry_z) + setup
    tbl = table(q.sort_values(["symbol", "expiry"]).to_dict("records"),
                [("contract", "Contract", None), ("bid", "Bid", fnum()), ("ask", "Ask", fnum()), ("last_price", "Last", fnum()),
                 ("px10", "₹/10 g 999 (mid)", fnum()), ("vs_settle_pct", "vs settlement", lambda v: f"{v:+.2f}%"),
                 ("volume", "Volume", fnum()), ("oi", "OI", fnum()),
                 ("last_trade_time", "Last trade (IST)", lambda v: "" if pd.isna(v) else pd.Timestamp(v).strftime("%d %b %H:%M:%S"))])
    status = info(esc(snap.message), "warn" if snap.stale else "ok", "schedule" if snap.stale else "bolt")
    return status + ui.scanner_cards_html(live.live_alerts(snap, ws.pairs, ws.curves, p.cfg(), p.roll_bdays), p.entry_z) + tbl


RENDER = {"overview": overview, "scanner": scanner, "curve": curve, "backtest": backtest, "tips": tips,
          "calendar": calendar, "data": data, "ask": ask, "live": live_page}
