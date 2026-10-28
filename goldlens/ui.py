"""GoldLens design system: theme CSS, chart template and HTML components.

Look and feel borrows from trading terminals: a ticker tape and dark charts (TradingView),
a compact market watch (Kite), strategy cards with clear P&L (Sensibull) and dense
labelled panels (Bloomberg/Koyfin). Gold is the accent; green/red only ever mean up/down.
"""
from __future__ import annotations

import base64
import html
import math

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------- palette
BG = "#0A0D14"
PANEL = "#10151F"
PANEL_2 = "#151C29"
BORDER = "#222B3A"
TEXT = "#E7E9EE"
MUTED = "#8A93A6"
GOLD = "#E0B04A"
GOLD_DEEP = "#B8862B"
UP = "#26C281"
DOWN = "#F0566A"
BLUE = "#5B8DEF"
VIOLET = "#A78BFA"

SYMBOL_COLORS = {"GOLDM": GOLD, "GOLDTEN": BLUE, "GOLDGUINEA": "#F07A8C", "GOLDPETAL": "#3CC9A7"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{--bg:#0A0D14;--panel:#10151F;--panel2:#151C29;--border:#222B3A;--text:#E7E9EE;--muted:#8A93A6;
--gold:#E0B04A;--gold2:#B8862B;--up:#26C281;--down:#F0566A;--blue:#5B8DEF;--violet:#A78BFA;}
html,body,[class*="css"],.stApp{font-family:'Inter',system-ui,sans-serif;}
.stApp{background:radial-gradient(1200px 500px at 85% -10%,rgba(224,176,74,.07),transparent 60%),
radial-gradient(900px 400px at -10% 10%,rgba(91,141,239,.05),transparent 60%),var(--bg);}
.block-container{padding-top:1.1rem;padding-bottom:3rem;max-width:1480px;}
header[data-testid="stHeader"]{background:transparent;}
[data-testid="stDecoration"]{display:none;}
h1,h2,h3{font-family:'Inter',sans-serif;letter-spacing:-.01em;}
.mono,.num{font-family:'JetBrains Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;}
/* sidebar */
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0E131C,#0A0D14);border-right:1px solid var(--border);}
section[data-testid="stSidebar"] .block-container{padding-top:1rem;}
/* tabs as a segmented nav */
.stTabs [data-baseweb="tab-list"]{gap:4px;background:var(--panel);border:1px solid var(--border);
border-radius:12px;padding:4px;overflow-x:auto;}
.stTabs [data-baseweb="tab"]{height:38px;padding:0 14px;border-radius:9px;color:var(--muted);font-weight:600;font-size:.86rem;}
.stTabs [data-baseweb="tab"]:hover{color:var(--text);background:rgba(255,255,255,.03);}
.stTabs [aria-selected="true"]{background:linear-gradient(180deg,rgba(224,176,74,.18),rgba(224,176,74,.08));
color:var(--gold)!important;box-shadow:inset 0 0 0 1px rgba(224,176,74,.35);}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none;}
.stTabs [data-baseweb="tab-panel"]{padding-top:18px;}
/* buttons */
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:600;border:1px solid var(--border);}
.stButton>button[kind="primary"]{background:linear-gradient(180deg,#F0C35E,#C9952F);color:#1A1306;border:0;
box-shadow:0 6px 20px -8px rgba(224,176,74,.6);}
.stButton>button[kind="primary"]:hover{filter:brightness(1.06);}
/* expanders, dataframes, alerts */
[data-testid="stExpander"]{border:1px solid var(--border);border-radius:12px;background:var(--panel);}
[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:12px;overflow:hidden;}
[data-testid="stAlertContainer"]{border-radius:12px;}
[data-testid="stPlotlyChart"]{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:6px 6px 0 6px;}
[data-testid="stChatMessage"]{background:var(--panel);border:1px solid var(--border);border-radius:14px;}
/* ---------- custom components ---------- */
.gl-top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:2px 0 10px 0;flex-wrap:wrap;}
.gl-brand{display:flex;align-items:center;gap:12px;}
.gl-brand h1{font-size:1.65rem;font-weight:800;margin:0;line-height:1;
background:linear-gradient(90deg,#F6D98B,#E0B04A 45%,#B8862B);-webkit-background-clip:text;background-clip:text;color:transparent;}
.gl-brand .tag{color:var(--muted);font-size:.8rem;margin-top:4px;}
.gl-pills{display:flex;gap:8px;flex-wrap:wrap;}
.gl-pill{display:inline-flex;align-items:center;gap:7px;padding:6px 11px;border-radius:999px;font-size:.76rem;font-weight:600;
background:var(--panel);border:1px solid var(--border);color:var(--muted);white-space:nowrap;}
.gl-pill b{color:var(--text);font-weight:600;}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;background:var(--muted);}
.dot.live{background:var(--up);box-shadow:0 0 0 0 rgba(38,194,129,.6);animation:pulse 1.8s infinite;}
.dot.gold{background:var(--gold);} .dot.blue{background:var(--blue);} .dot.violet{background:var(--violet);}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(38,194,129,.55);}70%{box-shadow:0 0 0 7px rgba(38,194,129,0);}100%{box-shadow:0 0 0 0 rgba(38,194,129,0);}}
/* ticker */
.gl-ticker{position:relative;overflow:hidden;border:1px solid var(--border);border-radius:12px;background:var(--panel);
margin-bottom:14px;mask-image:linear-gradient(90deg,transparent,#000 4%,#000 96%,transparent);}
.gl-ticker .track{display:inline-flex;gap:34px;padding:9px 0;white-space:nowrap;animation:scroll 48s linear infinite;}
.gl-ticker:hover .track{animation-play-state:paused;}
.gl-ticker .it{display:inline-flex;align-items:baseline;gap:8px;font-size:.82rem;}
.gl-ticker .sym{font-weight:700;color:var(--text);} .gl-ticker .sub{color:var(--muted);font-size:.72rem;}
.gl-ticker .px{font-family:'JetBrains Mono',monospace;color:var(--text);}
@keyframes scroll{from{transform:translateX(0);}to{transform:translateX(-50%);}}
.up{color:var(--up)!important;} .down{color:var(--down)!important;} .flat{color:var(--muted)!important;}
/* section header */
.gl-sec{margin:22px 0 10px 0;} .gl-sec .eb{color:var(--gold);font-size:.7rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;}
.gl-sec h3{margin:.15rem 0 0 0;font-size:1.22rem;font-weight:700;color:var(--text);}
.gl-sec p{margin:.25rem 0 0 0;color:var(--muted);font-size:.86rem;max-width:900px;}
/* KPI cards */
.gl-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;}
@media (max-width:1100px){.gl-kpis{grid-template-columns:repeat(2,minmax(0,1fr));}}
.gl-kpi{position:relative;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--border);
border-radius:14px;padding:14px 16px 10px 16px;overflow:hidden;}
.gl-kpi .lbl{color:var(--muted);font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;}
.gl-kpi .val{font-family:'JetBrains Mono',monospace;font-size:1.6rem;font-weight:600;color:var(--text);margin-top:6px;line-height:1.1;}
.gl-kpi .sub{font-size:.78rem;margin-top:4px;color:var(--muted);}
.gl-kpi .spark{width:100%;height:34px;margin-top:6px;display:block;}
.gl-kpi.accent{box-shadow:inset 0 1px 0 rgba(224,176,74,.25);}
.gl-kpi .glow{position:absolute;right:-30px;top:-30px;width:110px;height:110px;border-radius:50%;
background:radial-gradient(circle,rgba(224,176,74,.16),transparent 70%);}
/* panel */
.gl-panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px 16px;overflow-x:auto;}
.gl-panel h4{margin:0 0 8px 0;font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:700;}
/* market watch */
.gl-mw{width:100%;border-collapse:separate;border-spacing:0;font-size:.82rem;}
.gl-mw th{color:var(--muted);font-weight:600;font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;text-align:right;
padding:8px 7px;border-bottom:1px solid var(--border);white-space:nowrap;}
.gl-mw th:first-child,.gl-mw td:first-child{text-align:left;}
.gl-mw td{padding:10px 7px;white-space:nowrap;border-bottom:1px solid rgba(34,43,58,.6);text-align:right;font-family:'JetBrains Mono',monospace;color:var(--text);}
.gl-mw tr:last-child td{border-bottom:0;}
.gl-mw tr:hover td{background:rgba(255,255,255,.02);}
.gl-mw .s{font-family:'Inter',sans-serif;font-weight:700;display:flex;align-items:center;gap:9px;}
.gl-mw .s small{display:block;color:var(--muted);font-weight:500;font-size:.72rem;font-family:'JetBrains Mono',monospace;}
.gl-mw .sw{width:9px;height:26px;border-radius:3px;}
.gl-mw img.spark{width:76px;height:24px;vertical-align:middle;margin:0;}
.chip{display:inline-block;padding:2px 8px;border-radius:6px;font-size:.74rem;font-weight:600;font-family:'JetBrains Mono',monospace;
background:rgba(255,255,255,.04);border:1px solid var(--border);}
.chip.up{background:rgba(38,194,129,.1);border-color:rgba(38,194,129,.3);}
.chip.down{background:rgba(240,86,106,.1);border-color:rgba(240,86,106,.3);}
.chip.gold{color:var(--gold);background:rgba(224,176,74,.1);border-color:rgba(224,176,74,.3);}
/* scanner cards */
.gl-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;}
@media (max-width:1100px){.gl-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media (max-width:700px){.gl-grid,.gl-kpis{grid-template-columns:1fr;}}
.gl-card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--border);border-radius:14px;padding:14px 16px;position:relative;}
.gl-card.hot{border-color:rgba(38,194,129,.55);box-shadow:0 0 0 1px rgba(38,194,129,.25),0 10px 30px -12px rgba(38,194,129,.45);}
.gl-card.warm{border-color:rgba(224,176,74,.45);}
.gl-card .hd{display:flex;justify-content:space-between;align-items:center;gap:8px;}
.gl-card .pair{font-weight:800;font-size:.98rem;color:var(--text);} .gl-card .pair span{color:var(--muted);font-weight:500;}
.badge{font-size:.68rem;font-weight:700;padding:4px 9px;border-radius:999px;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap;}
.badge.alert{background:rgba(38,194,129,.15);color:var(--up);border:1px solid rgba(38,194,129,.4);}
.badge.flag{background:rgba(224,176,74,.12);color:var(--gold);border:1px solid rgba(224,176,74,.4);}
.badge.normal{background:rgba(138,147,166,.1);color:var(--muted);border:1px solid var(--border);}
.badge.illiquid{background:rgba(0,0,0,.25);color:#6B7385;border:1px solid var(--border);}
.badge.closed{background:rgba(167,139,250,.12);color:var(--violet);border:1px solid rgba(167,139,250,.35);}
.gl-card .row{display:flex;justify-content:space-between;align-items:baseline;margin-top:12px;}
.gl-card .z{font-family:'JetBrains Mono',monospace;font-size:1.5rem;font-weight:600;}
.gl-card .k{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;font-weight:600;}
.gauge{position:relative;height:8px;border-radius:99px;margin:8px 0 4px 0;
background:linear-gradient(90deg,rgba(240,86,106,.35) 0%,rgba(240,86,106,.08) var(--lo),rgba(255,255,255,.06) var(--lo),rgba(255,255,255,.06) var(--hi),rgba(240,86,106,.08) var(--hi),rgba(240,86,106,.35) 100%);}
.gauge .mid{position:absolute;left:50%;top:-3px;width:1px;height:14px;background:var(--muted);opacity:.5;}
.gauge .mk{position:absolute;top:50%;width:14px;height:14px;border-radius:50%;transform:translate(-50%,-50%);
background:var(--text);border:3px solid var(--bg);box-shadow:0 0 0 1px var(--text);}
.gauge.hotz .mk{background:var(--gold);box-shadow:0 0 0 1px var(--gold),0 0 12px rgba(224,176,74,.8);}
.scale{display:flex;justify-content:space-between;color:#5E6678;font-size:.62rem;font-family:'JetBrains Mono',monospace;}
.meter{position:relative;height:6px;border-radius:99px;background:rgba(255,255,255,.06);margin-top:6px;overflow:visible;}
.meter .fill{height:100%;border-radius:99px;background:linear-gradient(90deg,#3A4458,#5B667D);}
.meter .fill.ok{background:linear-gradient(90deg,#1E9E69,#26C281);}
.meter .hurdle{position:absolute;top:-4px;width:2px;height:14px;background:var(--gold);border-radius:2px;}
.gl-card .ft{display:flex;justify-content:space-between;gap:6px;margin-top:12px;padding-top:10px;border-top:1px dashed var(--border);
color:var(--muted);font-size:.72rem;font-family:'JetBrains Mono',monospace;}
/* edge funnel */
.funnel .st{display:grid;grid-template-columns:230px 1fr 130px 120px;grid-template-areas:"nm bw v d";align-items:center;gap:6px 12px;padding:9px 8px;border-bottom:1px dashed rgba(34,43,58,.8);}
.funnel .nm{grid-area:nm;} .funnel .bw{grid-area:bw;} .funnel .v{grid-area:v;} .funnel .d{grid-area:d;}
.funnel .st:last-child{border-bottom:0;}
.funnel .nm{font-size:.85rem;color:var(--text);font-weight:600;} .funnel .nm small{display:block;color:var(--muted);font-weight:500;font-size:.72rem;}
.funnel .bar{height:14px;border-radius:5px;background:linear-gradient(90deg,rgba(224,176,74,.85),rgba(224,176,74,.45));}
.funnel .bar.neg{background:linear-gradient(90deg,rgba(240,86,106,.9),rgba(240,86,106,.45));}
.funnel .v{font-family:'JetBrains Mono',monospace;text-align:right;font-weight:600;}
.funnel .d{text-align:right;}
.funnel .st.final{background:linear-gradient(90deg,rgba(224,176,74,.08),transparent);border-radius:10px;border:1px solid rgba(224,176,74,.35);}
@media (max-width:1000px){.funnel .st{grid-template-columns:1fr auto auto;grid-template-areas:"nm v d" "bw bw bw";}}
/* versus cards */
.vs{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.vs .c{border-radius:14px;padding:16px;border:1px solid var(--border);background:var(--panel);}
.vs .c.bad{border-color:rgba(240,86,106,.35);background:linear-gradient(180deg,rgba(240,86,106,.07),var(--panel));}
.vs .c.good{border-color:rgba(38,194,129,.35);background:linear-gradient(180deg,rgba(38,194,129,.07),var(--panel));}
.vs .big{font-family:'JetBrains Mono',monospace;font-size:2rem;font-weight:600;margin:6px 0;}
.vs .lbl{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:700;}
.vs .bar{height:8px;border-radius:99px;background:rgba(255,255,255,.06);margin-top:10px;overflow:hidden;}
.vs .bar i{display:block;height:100%;border-radius:99px;}
/* checklist */
.checks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
.checks .ck{display:flex;gap:12px;align-items:flex-start;background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:12px 14px;}
.checks .ic{flex:none;width:26px;height:26px;border-radius:8px;display:grid;place-items:center;background:rgba(38,194,129,.12);color:var(--up);font-weight:800;}
.checks b{color:var(--text);font-size:.88rem;} .checks p{margin:2px 0 0 0;color:var(--muted);font-size:.8rem;}
.checks .n{margin-left:auto;font-family:'JetBrains Mono',monospace;color:var(--gold);font-weight:600;white-space:nowrap;}
@media (max-width:800px){.checks,.vs{grid-template-columns:1fr;}}
/* brief */
.gl-brief{background:linear-gradient(180deg,rgba(224,176,74,.06),var(--panel));border:1px solid rgba(224,176,74,.25);border-radius:14px;padding:14px 18px;}
.gl-brief .hd{display:flex;flex-direction:column;gap:2px;margin-bottom:6px;}
.gl-brief .ttl{font-weight:700;color:var(--text);} .gl-brief .by{color:var(--muted);font-size:.75rem;}
.foot{color:var(--muted);font-size:.78rem;margin-top:6px;}
/* tip checker */
.verdict{border-radius:16px;padding:18px 20px;border:1px solid var(--border);position:relative;overflow:hidden;}
.verdict .t{font-size:1.45rem;font-weight:800;color:var(--text);} .verdict .d{color:#C9CED8;margin-top:6px;font-size:.92rem;}
.verdict .stamp{position:absolute;right:18px;top:14px;font-family:'JetBrains Mono',monospace;font-size:.7rem;letter-spacing:.14em;
text-transform:uppercase;padding:4px 10px;border-radius:999px;border:1px solid currentColor;opacity:.9;}
.verdict.fail{background:linear-gradient(135deg,rgba(240,86,106,.16),var(--panel) 60%);border-color:rgba(240,86,106,.45);} .verdict.fail .stamp{color:var(--down);}
.verdict.hype,.verdict.thin{background:linear-gradient(135deg,rgba(224,176,74,.16),var(--panel) 60%);border-color:rgba(224,176,74,.45);}
.verdict.hype .stamp,.verdict.thin .stamp{color:var(--gold);}
.verdict.pass{background:linear-gradient(135deg,rgba(38,194,129,.16),var(--panel) 60%);border-color:rgba(38,194,129,.45);} .verdict.pass .stamp{color:var(--up);}
.verdict.never{background:linear-gradient(135deg,rgba(167,139,250,.16),var(--panel) 60%);border-color:rgba(167,139,250,.45);} .verdict.never .stamp{color:var(--violet);}
.flags{margin-top:12px;display:flex;flex-direction:column;gap:6px;}
.flags div{font-size:.84rem;color:#F3C1C8;background:rgba(240,86,106,.08);border:1px solid rgba(240,86,106,.25);border-radius:10px;padding:7px 10px;}
.rulebox{font-family:'JetBrains Mono',monospace;font-size:.85rem;color:var(--text);background:var(--panel2);border:1px dashed rgba(224,176,74,.45);
border-radius:12px;padding:12px 14px;}
.rulebox .src{font-family:'Inter',sans-serif;color:var(--muted);font-size:.74rem;margin-top:6px;}
.bd .r{display:grid;grid-template-columns:1fr auto;grid-template-areas:"n p" "b b";gap:6px 12px;align-items:center;padding:8px 0;}
.bd .r .n{grid-area:n;} .bd .r .p{grid-area:p;} .bd .r .b{grid-area:b;}
.bd .r .n{font-size:.86rem;color:var(--text);} .bd .r .p{font-family:'JetBrains Mono',monospace;text-align:right;color:var(--gold);font-weight:600;}
.bd .r .b{height:10px;border-radius:99px;background:rgba(255,255,255,.06);overflow:hidden;} .bd .r .b i{display:block;height:100%;border-radius:99px;
background:linear-gradient(90deg,#F0566A,#E0B04A);}
/* telegram phone preview */
.phone{max-width:370px;margin:0 auto;border-radius:38px;padding:11px;background:#05070B;border:1px solid #2A3446;
box-shadow:0 40px 90px -40px rgba(0,0,0,.9),inset 0 0 0 2px #121826;}
.phone .scr{border-radius:28px;overflow:hidden;background:#0E1621;}
.phone .top{display:flex;justify-content:space-between;padding:8px 18px 4px;color:#C8D1DA;font-size:.7rem;font-weight:600;background:#17212B;}
.phone .bar{display:flex;align-items:center;gap:10px;padding:8px 14px 10px;background:#17212B;border-bottom:1px solid #0B121A;}
.phone .av{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#F6D98B,#B8862B);font-size:1.1rem;}
.phone .nm{color:#fff;font-weight:600;font-size:.9rem;line-height:1.1;} .phone .nm small{display:block;color:#7D8E9E;font-weight:400;font-size:.72rem;}
.phone .chat{padding:16px 12px 20px;min-height:430px;background:radial-gradient(circle at 20% 10%,rgba(91,141,239,.06),transparent 40%),#0E1621;}
.phone .msg{background:#182533;color:#E9EDF1;border-radius:16px 16px 16px 5px;padding:10px 12px 6px;font-size:.82rem;line-height:1.5;
max-width:96%;box-shadow:0 1px 0 rgba(0,0,0,.3);}
.phone .msg b{color:#fff;} .phone .msg i{color:#8CA0B3;} .phone .msg a{color:#6AB2F2;text-decoration:none;}
.phone .msg code{font-family:'JetBrains Mono',monospace;font-size:.76rem;}
.phone .tm{text-align:right;color:#6D7F8F;font-size:.66rem;margin-top:2px;}
</style>
"""

LOGO = """<svg width="38" height="38" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="g" x1="6" y1="4" x2="42" y2="44"><stop stop-color="#F8DE92"/><stop offset=".55" stop-color="#E0B04A"/><stop offset="1" stop-color="#9C6E1F"/></linearGradient></defs>
<circle cx="21" cy="21" r="15" fill="url(#g)"/><circle cx="21" cy="21" r="10.5" fill="none" stroke="#0A0D14" stroke-opacity=".35" stroke-width="1.6"/>
<path d="M14.5 24.5l4-4 3 2.5 6-6.5" stroke="#0A0D14" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M32 32l9 9" stroke="#E0B04A" stroke-width="4.5" stroke-linecap="round"/></svg>"""


def svg_img(svg: str, cls: str = "", style: str = "") -> str:
    """st.html strips inline <svg>; an <img> with a data: URI survives the sanitiser."""
    if 'xmlns=' not in svg:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    data = base64.b64encode(svg.encode()).decode()
    return f'<img class="{cls}" style="{style}" src="data:image/svg+xml;base64,{data}" alt=""/>'


LOGO_IMG = svg_img(LOGO, style="width:38px;height:38px")


# ---------------------------------------------------------------- helpers
def inject():
    st.html(CSS)
    pio.templates["goldlens"] = _template()
    pio.templates.default = "goldlens"


def esc(s) -> str:
    return html.escape(str(s))


def inr(x, signed: bool = False, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    sign = ("+" if x > 0 else "−" if x < 0 else "") if signed else ("−" if x < 0 else "")
    v = abs(x)
    if v >= 1e7:
        return f"{sign}₹{v / 1e7:,.{decimals}f} cr"
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:,.{decimals}f} lakh"
    return f"{sign}₹{v:,.0f}"


def num(x, d: int = 2) -> str:
    """Fixed decimals without a misleading "-0.00"."""
    v = round(float(x), d)
    return f"{(0.0 if v == 0 else v):.{d}f}"


def tone(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)) or abs(x) < 1e-12:
        return "flat"
    return "up" if x > 0 else "down"


def arrow(x) -> str:
    return {"up": "▲", "down": "▼"}.get(tone(x), "■")


def sparkline(values, color: str = GOLD, w: int = 160, h: int = 34, fill: bool = True) -> str:
    v = [float(x) for x in values if x is not None and x == x]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1.0
    pts = [(i * w / (len(v) - 1), h - 3 - (x - lo) / rng * (h - 6)) for i, x in enumerate(v)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f'<polygon points="0,{h} {line} {w},{h}" fill="{color}" opacity=".13"/>' if fill else ""
    lx, ly = pts[-1]
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="none">{area}'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.7" '
           f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
           f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.4" fill="{color}"/></svg>')
    return svg_img(svg, "spark")


def _template() -> go.layout.Template:
    axis = dict(gridcolor="#1B2332", zerolinecolor="#2A3446", linecolor="#222B3A", tickcolor="#222B3A",
                tickfont=dict(color=MUTED, size=11), title=dict(font=dict(color=MUTED, size=11)),
                showspikes=True, spikecolor="#3A4458", spikethickness=1, spikedash="dot", spikemode="across",
                automargin=True)
    return go.layout.Template(layout=dict(
        font=dict(family="Inter, system-ui, sans-serif", color="#C9CED8", size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=[GOLD, BLUE, "#F07A8C", "#3CC9A7", VIOLET, "#F59E0B", "#94A3B8"],
        xaxis=axis, yaxis=axis, hovermode="x unified",
        hoverlabel=dict(bgcolor=PANEL_2, bordercolor=GOLD_DEEP, font=dict(family="JetBrains Mono, monospace", color=TEXT, size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, size=11), title=dict(text="")),
        title=dict(font=dict(size=14, color=TEXT), x=0.01, xanchor="left"),
        margin=dict(l=12, r=12, t=40, b=12),
    ))


def chart(fig: go.Figure, height: int = 360, key: str | None = None):
    fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", theme=None, key=key,
                    config={"displayModeBar": False, "scrollZoom": False})


# ---------------------------------------------------------------- components
def header_html(as_of: str, data_span: str, ai_label: str, ai_on: bool, live_on: bool) -> str:
    ai_dot = "gold" if ai_on else ""
    live = ('<span class="gl-pill"><span class="dot live"></span><b>LIVE</b> Upstox</span>' if live_on else
            '<span class="gl-pill"><span class="dot blue"></span><b>EOD</b> MCX Bhavcopy</span>')
    return (f"""<div class="gl-top"><div class="gl-brand">{LOGO_IMG}<div><h1>GoldLens</h1>
<div class="tag">Relative-value intelligence for MCX gold futures · PS 03</div></div></div>
<div class="gl-pills">{live}<span class="gl-pill">Settlement <b>{esc(as_of)}</b></span>
<span class="gl-pill">History <b>{esc(data_span)}</b></span>
<span class="gl-pill"><span class="dot {ai_dot}"></span>AI <b>{esc(ai_label)}</b></span></div></div>""")


def ticker_html(items: list[dict]) -> str:
    """items: sym, sub, px, chg (pct) — rendered twice for a seamless loop."""
    def one(i):
        chg = i.get("chg")
        c = f'<span class="{tone(chg)}">{arrow(chg)} {chg:+.2f}%</span>' if chg is not None else ""
        return (f'<span class="it"><span class="sym">{esc(i["sym"])}</span><span class="sub">{esc(i.get("sub", ""))}</span>'
                f'<span class="px">{esc(i["px"])}</span>{c}</span>')
    body = "".join(one(i) for i in items)
    return (f'<div class="gl-ticker"><div class="track">{body}{body}</div></div>')


def section_html(title: str, subtitle: str = "", eyebrow: str = "") -> str:
    eb = f'<div class="eb">{esc(eyebrow)}</div>' if eyebrow else ""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return (f'<div class="gl-sec">{eb}<h3>{esc(title)}</h3>{sub}</div>')


def kpis_html(cards: list[dict]) -> str:
    """cards: label, value, sub (html ok), spark (list), color, accent."""
    out = []
    for c in cards:
        spark = sparkline(c["spark"], c.get("color", GOLD)) if c.get("spark") is not None else ""
        glow = '<div class="glow"></div>' if c.get("accent") else ""
        out.append(f'<div class="gl-kpi{" accent" if c.get("accent") else ""}">{glow}<div class="lbl">{esc(c["label"])}</div>'
                   f'<div class="val">{c["value"]}</div><div class="sub">{c.get("sub", "")}</div>{spark}</div>')
    return (f'<div class="gl-kpis">{"".join(out)}</div>')


def market_watch_html(rows: list[dict], title: str = "Market watch") -> str:
    """rows: symbol, contract, quoted, px10, chg, premium, volume, oi, spark."""
    trs = []
    for r in rows:
        col = SYMBOL_COLORS.get(r["symbol"], GOLD)
        prem = r.get("premium")
        prem_chip = ('<span class="chip gold">ref</span>' if prem is None else
                     f'<span class="chip {tone(prem)}">{prem:+.0f} bps</span>')
        chg = r.get("chg")
        trs.append(
            f'<tr><td><div class="s"><span class="sw" style="background:{col}"></span><div>{esc(r["symbol"])}'
            f'<small>{esc(r["contract"])}</small></div></div></td>'
            f'<td>{r["quoted"]:,.0f}</td><td>{r["px10"]:,.0f}</td>'
            f'<td class="{tone(chg)}">{arrow(chg)} {chg:+.2f}%</td><td>{prem_chip}</td>'
            f'<td>{r["volume"]:,.0f}</td><td>{r["oi"]:,.0f}</td>'
            f'<td>{sparkline(r["spark"], col, 76, 24, fill=False)}</td></tr>')
    return (f'<div class="gl-panel"><h4>{esc(title)}</h4><table class="gl-mw"><thead><tr>'
            '<th>Contract</th><th>Quoted</th><th>₹/10g 999</th><th>Day</th><th>vs GOLDM</th>'
            '<th>Volume</th><th>OI</th><th>60 d</th></tr></thead><tbody>'
            + "".join(trs) + "</tbody></table></div>")


BADGE = {"ALERT": ("alert", "Alert"), "Flagged, below cost": ("flag", "Flagged · below cost"),
         "Normal": ("normal", "Normal"), "Illiquid: no signal": ("illiquid", "Illiquid"),
         "Market closed": ("closed", "Market closed")}


def scanner_cards_html(rows: list[dict], entry_z: float, cost_margin: float = 1.5) -> str:
    cards = []
    lo = (4 - entry_z) / 8 * 100
    hi = (4 + entry_z) / 8 * 100
    for r in rows:
        cls, label = BADGE.get(r["status"], ("normal", r["status"]))
        z = r.get("z")
        z_ok = z is not None and z == z
        pos = (max(-4, min(4, z)) + 4) / 8 * 100 if z_ok else 50
        hot = z_ok and abs(z) >= entry_z
        edge, cost = r.get("edge_rs"), r.get("round_trip_cost_rs") or 0
        ratio = (edge / cost) if (edge is not None and cost) else 0
        fill = min(ratio / (2 * cost_margin), 1) * 100
        card_cls = "hot" if r["status"] == "ALERT" else ("warm" if r["status"].startswith("Flagged") else "")
        a, b = r["pair"].split("/")
        rich = f'rich leg <b style="color:var(--text)">{esc(r["rich"])}</b>' if r.get("rich") else "no signal"
        spread = r.get("spread_bps")
        mean = r.get("mean_bps")
        cards.append(f"""<div class="gl-card {card_cls}"><div class="hd"><div class="pair">{esc(a)} <span>/ {esc(b)}</span></div>
<span class="badge {cls}">{label}</span></div>
<div class="row"><div><div class="k">z-score</div><div class="z {'up' if hot else ''}">{(f'{z:+.2f}' if z_ok else 'n/a')}</div></div>
<div style="text-align:right"><div class="k">spread · mean</div><div class="mono" style="font-size:.86rem">{(f'{spread:+.1f}' if spread is not None else 'n/a')} · {(f'{mean:+.1f}' if mean is not None else 'n/a')} bps</div></div></div>
<div class="gauge {'hotz' if hot else ''}" style="--lo:{lo:.1f}%;--hi:{hi:.1f}%"><div class="mid"></div><div class="mk" style="left:{pos:.1f}%"></div></div>
<div class="scale"><span>−4σ</span><span>−{entry_z:g}</span><span>0</span><span>+{entry_z:g}</span><span>+4σ</span></div>
<div class="row" style="margin-top:12px"><div class="k">Edge vs cost hurdle</div><div class="mono" style="font-size:.8rem">{inr(edge) if edge is not None else 'n/a'} / {inr(cost)}</div></div>
<div class="meter"><div class="fill {'ok' if (hot and ratio >= cost_margin) else ''}" style="width:{fill:.1f}%"></div><div class="hurdle" style="left:50%"></div></div>
<div class="ft"><span>{esc(r.get('leg_a', ''))} · {esc(r.get('leg_b', ''))}</span><span>{rich}</span></div></div>""")
    return (f'<div class="gl-grid">{"".join(cards)}</div>')


def funnel_html(steps: list[tuple[str, str, float]]) -> str:
    """steps: (name, explanation, net P&L). Last step is the honest result."""
    mx = max(abs(v) for _, _, v in steps) or 1
    rows = []
    prev = None
    for i, (name, note, v) in enumerate(steps):
        w = max(abs(v) / mx * 100, 1.2)
        d = "" if prev is None else f'<span class="chip {tone(v - prev)}">{inr(v - prev, signed=True)}</span>'
        final = " final" if i == len(steps) - 1 else ""
        rows.append(f'<div class="st{final}"><div class="nm">{esc(name)}<small>{esc(note)}</small></div>'
                    f'<div class="bw"><div class="bar{" neg" if v < 0 else ""}" style="width:{w:.1f}%"></div></div>'
                    f'<div class="v {tone(v)}">{inr(v, signed=True)}</div><div class="d">{d}</div></div>')
        prev = v
    return (f'<div class="gl-panel funnel">{"".join(rows)}</div>')


def versus_html(left: dict, right: dict) -> str:
    def card(c, cls):
        return (f'<div class="c {cls}"><div class="lbl">{esc(c["label"])}</div><div class="big">{c["value"]}</div>'
                f'<div class="foot">{c["sub"]}</div><div class="bar"><i style="width:{c["pct"]:.0f}%;background:{c["color"]}"></i></div></div>')
    return (f'<div class="vs">{card(left, "bad")}{card(right, "good")}</div>')


def checklist_html(items: list[tuple[str, str, str]]) -> str:
    rows = "".join(f'<div class="ck"><div class="ic">✓</div><div><b>{esc(t)}</b><p>{d}</p></div>'
                   f'<div class="n">{esc(n)}</div></div>' for t, d, n in items)
    return (f'<div class="checks">{rows}</div>')


STAMP = {"fail": "Busted", "hype": "Overhyped", "thin": "Unproven", "pass": "Holds up", "never": "Never fires"}


def verdict_html(kind: str, title: str, detail: str, flags: list[str] | None = None) -> str:
    fl = "".join(f"<div>🚩 {esc(f)}</div>" for f in (flags or []))
    return (f'<div class="verdict {kind}"><span class="stamp">{STAMP.get(kind, kind)}</span>'
            f'<div class="t">{esc(title)}</div><div class="d">{esc(detail)}</div>'
            f'{f"<div class=flags>{fl}</div>" if fl else ""}</div>')


def rulebox_html(text: str, source: str) -> str:
    return (f'<div class="rulebox">{esc(text)}<div class="src">Read by {esc(source)} · edit any field below</div></div>')


def breakdown_html(items: list[tuple[str, float, float]]) -> str:
    """items: (reason, rupees, share %)."""
    rows = "".join(f'<div class="r"><div class="n">{esc(r)}<br><span class="mono" style="color:var(--muted);font-size:.74rem">'
                   f'{inr(d)}</span></div><div class="b"><i style="width:{p:.0f}%"></i></div><div class="p">{p:.0f}%</div></div>'
                   for r, d, p in items)
    return (f'<div class="gl-panel bd"><h4>Where the paper profit went</h4>{rows}</div>')


def phone_html(message_html: str, bot_name: str = "GoldLens Bot", time_str: str = "08:30") -> str:
    """A Telegram-style phone mockup showing exactly what will be sent."""
    body = message_html.replace("\n", "<br>")
    return (f'<div class="phone"><div class="scr"><div class="top"><span>{esc(time_str)}</span><span>▮▮▮ 5G 🔋</span></div>'
            f'<div class="bar"><div class="av">🪙</div><div class="nm">{esc(bot_name or "GoldLens Bot")}<small>bot</small></div></div>'
            f'<div class="chat"><div class="msg">{body}<div class="tm">{esc(time_str)} ✓✓</div></div></div></div></div>')


# ---------------------------------------------------------------- Streamlit wrappers
def header(*args, **kwargs):
    st.html(header_html(*args, **kwargs))


def ticker(*args, **kwargs):
    st.html(ticker_html(*args, **kwargs))


def section(*args, **kwargs):
    st.html(section_html(*args, **kwargs))


def kpis(*args, **kwargs):
    st.html(kpis_html(*args, **kwargs))


def market_watch(*args, **kwargs):
    st.html(market_watch_html(*args, **kwargs))


def scanner_cards(*args, **kwargs):
    st.html(scanner_cards_html(*args, **kwargs))


def funnel(*args, **kwargs):
    st.html(funnel_html(*args, **kwargs))


def versus(*args, **kwargs):
    st.html(versus_html(*args, **kwargs))


def checklist(*args, **kwargs):
    st.html(checklist_html(*args, **kwargs))


def verdict(*args, **kwargs):
    st.html(verdict_html(*args, **kwargs))


def rulebox(*args, **kwargs):
    st.html(rulebox_html(*args, **kwargs))


def breakdown(*args, **kwargs):
    st.html(breakdown_html(*args, **kwargs))


def phone(*args, **kwargs):
    st.html(phone_html(*args, **kwargs))
