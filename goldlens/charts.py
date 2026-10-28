"""Plotly figures shared by the website and the Streamlit dashboard.

Every function returns a go.Figure styled by the "goldlens" template (see ui.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from .config import SYMBOLS
from .ui import BLUE, DOWN, GOLD, MUTED, UP, SYMBOL_COLORS as COLORS, _template

pio.templates["goldlens"] = _template()


def _fig(height: int, **layout) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(template="goldlens", height=height, **layout)
    return fig


def normalise(ws, mode: str = "px10", days: int = 365) -> go.Figure:
    """Front contracts as quoted (mode='close') or on GoldLens's one scale (mode='px10')."""
    fr = ws.front.reset_index()
    fr = fr[fr["date"] >= fr["date"].max() - pd.Timedelta(days=days)]
    fig = _fig(400, yaxis_title="Quoted price (₹)" if mode == "close" else "₹ per 10 g of 999 gold",
               yaxis_tickformat=",.0f")
    for sym in SYMBOLS:
        s = fr[fr["symbol"] == sym]
        fig.add_trace(go.Scatter(x=s["date"], y=s[mode], name=sym, mode="lines", line=dict(color=COLORS[sym], width=1.8)))
    return fig


def pair(res, window: int, entry_z: float, a: str, b: str) -> go.Figure:
    sig = res.signal
    mean = sig["spread"].shift(1).rolling(window, min_periods=window // 2).mean()
    sd = sig["spread"].shift(1).rolling(window, min_periods=window // 2).std()
    fig = _fig(400, yaxis_title=f"ln({a} / {b}) after carry · bps")
    fig.add_trace(go.Scatter(x=sig.index, y=mean + entry_z * sd, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=sig.index, y=mean - entry_z * sd, line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(224,176,74,0.10)", name=f"±{entry_z:g}σ band", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=sig.index, y=mean, line=dict(color=GOLD, dash="dot", width=1), name="Rolling mean"))
    fig.add_trace(go.Scatter(x=sig.index, y=sig["spread"], line=dict(color=BLUE, width=1.5), name="Spread (bps)"))
    if not res.trades.empty:
        t = res.trades
        fig.add_trace(go.Scatter(x=t["entry_date"], y=sig["spread"].reindex(t["entry_date"]).to_numpy(), mode="markers",
                                 name="Entry", marker=dict(symbol="triangle-up", size=10, color=UP)))
        fig.add_trace(go.Scatter(x=t["exit_date"], y=sig["spread"].reindex(t["exit_date"]).to_numpy(), mode="markers",
                                 name="Exit", marker=dict(symbol="x-thin", size=9, color=DOWN, line=dict(width=2, color=DOWN))))
    return fig


def premiums(curves: pd.DataFrame) -> go.Figure:
    cols = [c for c in curves.columns if c.startswith("premium_")]
    prem = curves[cols].rename(columns=lambda c: c.replace("premium_", "")).rolling(5, min_periods=1).median()
    fig = _fig(340, yaxis_title="bps vs GOLDM")
    for sym in prem.columns:
        fig.add_trace(go.Scatter(x=prem.index, y=prem[sym], name=sym, line=dict(color=COLORS[sym], width=1.6)))
    fig.add_hline(y=0, line_color=GOLD, line_dash="dot", annotation_text="GOLDM", annotation_font_color=GOLD)
    return fig


def term_structure(ws, day) -> go.Figure:
    snap = ws.df[(ws.df["date"] == day) & ws.df["traded"]]
    c = ws.curves.loc[day]
    fig = _fig(420, yaxis_title="₹ per 10 g of 999 gold", yaxis_tickformat=",.0f", hovermode="closest")
    taus = np.linspace(0, max(snap["tau"].max(), 0.1), 60)
    fig.add_trace(go.Scatter(x=day + pd.to_timedelta(taus * 365, unit="D"), y=np.exp(c["ln_s"] + c["carry"] * taus),
                             name="Fair curve (GOLDM basis)", line=dict(color=GOLD, dash="dash", width=1.5)))
    for sym in SYMBOLS:
        s = snap[snap["symbol"] == sym]
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s["expiry"], y=s["px10"], mode="markers", name=sym,
            marker=dict(color=COLORS[sym], size=np.clip(np.sqrt(s["volume"]) / 4, 7, 26), opacity=.8,
                        line=dict(width=1, color="#0A0D14")),
            customdata=s[["contract", "volume"]],
            hovertemplate="%{customdata[0]}<br>₹%{y:,.0f}<br>vol %{customdata[1]:,.0f}<extra></extra>"))
    return fig


def carry(curves: pd.DataFrame) -> go.Figure:
    fig = _fig(300, title="Market-implied carry, % a year", showlegend=False)
    fig.add_trace(go.Scatter(x=curves.index, y=curves["carry"] * 100, line=dict(color=BLUE, width=1.5),
                             fill="tozeroy", fillcolor="rgba(91,141,239,.08)", name="carry"))
    return fig


def rolldown(dec: dict) -> go.Figure:
    fig = _fig(300, title="Why the contract moved, bps", showlegend=False, hovermode="closest")
    fig.add_trace(go.Waterfall(x=["Spot shift", "Carry change", "Roll-down", "Total"],
                               y=[dec["level_bps"], dec["carry_shift_bps"], dec["rolldown_bps"], dec["total_bps"]],
                               measure=["relative", "relative", "relative", "total"],
                               increasing=dict(marker_color=UP), decreasing=dict(marker_color=DOWN),
                               totals=dict(marker_color=GOLD), connector=dict(line=dict(color="#3A4458"))))
    return fig


def ladder_equity(ladder: list) -> go.Figure:
    """ladder: list of (name, daily total Series, totals)."""
    fig = _fig(400, title="Cumulative net P&L for each step (₹)", yaxis_tickformat=",.0f", legend=dict(font=dict(size=10)))
    for i, (name, daily, _) in enumerate(ladder):
        last = i == len(ladder) - 1
        fig.add_trace(go.Scatter(x=daily.index, y=daily.cumsum(), name=name,
                                 line=dict(width=3 if last else 1.1, color=GOLD if last else None), opacity=1 if last else .55))
    return fig


def equity(daily_net: pd.Series, title: str = "Cumulative net P&L (₹)") -> go.Figure:
    fig = _fig(300, title=title, yaxis_tickformat=",.0f", showlegend=False)
    cum = daily_net.cumsum()
    color = UP if cum.iloc[-1] >= 0 else DOWN
    fig.add_trace(go.Scatter(x=cum.index, y=cum, line=dict(color=color, width=2), fill="tozeroy",
                             fillcolor="rgba(38,194,129,.06)" if color == UP else "rgba(240,86,106,.06)"))
    return fig


def tip_equity(ev: dict) -> go.Figure:
    nv, hn = ev["naive"]["result"].daily["net"], ev["honest"]["result"].daily["net"]
    fig = _fig(300, title="Cumulative P&L, ₹", yaxis_tickformat=",.0f")
    fig.add_trace(go.Scatter(x=nv.index, y=nv.cumsum(), name="Tipster-style", line=dict(color=MUTED, width=1.4, dash="dot")))
    fig.add_trace(go.Scatter(x=hn.index, y=hn.cumsum(), name="Honest", line=dict(color=GOLD, width=2.6)))
    return fig


def calendar(cal: pd.DataFrame, last_day) -> go.Figure:
    recent = cal[cal["expiry"] >= last_day - pd.Timedelta(days=200)].sort_values(["symbol", "expiry"])
    fig = _fig(max(420, 24 * len(recent)), barmode="overlay", hovermode="closest", bargap=.35)
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
    return fig


def fit_error(curves: pd.DataFrame) -> go.Figure:
    fig = _fig(260, title="Daily curve-fit error, bps (5-day median)", showlegend=False)
    fig.add_trace(go.Scatter(x=curves.index, y=curves["fit_rmse_bps"].rolling(5, min_periods=1).median(),
                             line=dict(color="#A78BFA", width=1.4), fill="tozeroy", fillcolor="rgba(167,139,250,.08)"))
    return fig
