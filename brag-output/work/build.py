"""Build the GoldLens elevator-pitch composition from real GoldLens data, components and voice timings."""
import html
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(r"D:\HackonHills")
OUT = ROOT / "brag-output" / "composition"
sys.path.insert(0, str(ROOT))

from goldlens import notify, tipcheck, ui  # noqa: E402
from goldlens.config import SPECS, SYMBOLS  # noqa: E402
from goldlens.sitedata import build_site_data  # noqa: E402
from goldlens.web import state  # noqa: E402
from goldlens.web.state import Params  # noqa: E402

VO = [
    "Hack in Hills, powered by TinyFish. We're Team TechFast, and this is GoldLens.",
    "M C X sells the same gold four ways. Different lot sizes, different purity, and four prices that look completely unrelated.",
    "GoldLens puts every contract on one scale: rupees per ten grams of pure gold. Four lines become one.",
    "Then it flags only the gaps that are truly unusual, and that would still pay after real trading costs.",
    "Most backtests lie. Ours removes each mistake, one by one. Twenty five lakh rupees of paper profit becomes a small loss. That's the honest truth.",
    "So we built a lie detector for trading tips. Paste any tip, even in Hinglish. This one promised forty percent a year. Busted.",
    "And every morning, one clear brief lands on your phone, in English or Hindi.",
    "GoldLens. Honest intelligence for gold traders.",
]
LEAD = [0.6, 0.4, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3]     # silence before each line, inside its scene
TAIL = [0.7, 0.5, 0.6, 0.5, 0.6, 0.7, 0.6, 2.6]     # breathing room after each line
COLORS = {"GOLDM": "#E0B04A", "GOLDTEN": "#5B8DEF", "GOLDGUINEA": "#F07A8C", "GOLDPETAL": "#3CC9A7"}


def wav_len(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- timing from the real voice
durs = [wav_len(OUT / "assets" / "vo" / f"vo{i + 1}.wav") for i in range(8)]
scenes, t = [], 0.0
for i, d in enumerate(durs):
    dur = round(LEAD[i] + d + TAIL[i], 2)
    scenes.append({"id": f"s{i + 1}", "start": round(t, 2), "dur": dur, "vo": round(t + LEAD[i], 2), "vodur": d})
    t += dur
TOTAL = round(t, 2)
S = [s["start"] for s in scenes]


def at(i: int, phrase: str, offset: float = 0.0) -> float:
    """Approximate when a phrase is spoken: proportional to its character position in the line."""
    text = VO[i]
    k = text.index(phrase)
    return round(scenes[i]["vo"] + scenes[i]["vodur"] * k / len(text) + offset, 2)


K = {
    "presents": at(0, "We're"),
    "wordmark": at(0, "GoldLens", -0.15),
    "cards": [round(at(1, "four ways") + 0.7 * j, 2) for j in range(4)],
    "morph": at(2, "one scale", 0.2),
    "scan": [round(S[3] + 1.0 + 0.6 * j, 2) for j in range(3)],
    "rows": [round(S[4] + 1.0, 2), at(4, "one by one"), at(4, "becomes a small loss", -0.2)],
    "truth": at(4, "That's"),
    "type": round(S[5] + 0.6, 2), "typeDur": 2.4,
    "rule": at(5, "Paste any tip"),
    "verdict": at(5, "This one promised", -0.3),
    "stamp": at(5, "Busted", -0.05),
}

# ---------------------------------------------------------------- real data
p = Params()
ws = state.workspace(p.roll_bdays)
rows, honest, facts = state.today(p)
watch = state.watch(p.roll_bdays)
site = build_site_data(ws)
lad = {n: tot["net_pnl"] for n, _, tot in state.ladder(p)}
nets = [lad["+ past-only z-score"], lad["+ real contracts & carry"], lad["+ liquidity filter (honest)"]]

# contract cards
cards = []
for r in watch:
    sp = SPECS[r["symbol"]]
    cards.append(f'<div class="ccard"><span class="sw" style="background:{COLORS[r["symbol"]]}"></span>'
                 f'<div class="sym">{r["symbol"]}</div>'
                 f'<div class="spec">{sp.lot_grams:g} g lot · per {sp.quote_grams:g} g · {sp.purity:g}</div>'
                 f'<div class="px">₹{r["quoted"]:,.0f}<small>{r["contract"]}</small></div></div>')

# chart: quoted vs normalised paths, same point structure so GSAP can morph them
SER = site["series"]
W, H, PL, PR, PT, PB = 1640, 560, 120, 20, 20, 40
n = len(SER["dates"])


def rng(key, pad):
    vals = [v for s in SYMBOLS for v in SER[s][key] if v is not None]
    lo, hi = min(vals), max(vals)
    return lo - (hi - lo) * pad, hi + (hi - lo) * pad


qR, nR = rng("quoted", 0.04), rng("px10", 0.06)
X = lambda i: PL + i * (W - PL - PR) / (n - 1)
Y = lambda v, r: PT + (1 - (v - r[0]) / (r[1] - r[0])) * (H - PT - PB)
path = lambda vals, r: " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v, r):.1f}" for i, v in enumerate(vals))


def grid(r, cls, hidden):
    out = [f'<g class="gl {cls}"' + (' style="opacity:0"' if hidden else "") + ">"]
    for j in range(5):
        v = r[0] + (r[1] - r[0]) * j / 4
        y = Y(v, r)
        out.append(f'<line x1="{PL}" x2="{W - PR}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text x="{PL - 14}" y="{y + 7:.1f}" text-anchor="end">₹{round(v / 1000):,}k</text>')
    return "".join(out) + "</g>"


chart = grid(qR, "gq", False) + grid(nR, "gn", True)
chart += "".join(f'<path class="series" stroke="{COLORS[s]}" d="{path(SER[s]["quoted"], qR)}"/>' for s in SYMBOLS)
paths = {"norm": [path(SER[s]["px10"], nR) for s in SYMBOLS]}
legend = "".join(f'<span><i style="background:{COLORS[s]}"></i>{s}</span>' for s in SYMBOLS)

# tip checker on the real example
tip_text = re.sub(r"\s*🚀", "", tipcheck.EXAMPLES[0]).strip()
rule = tipcheck.parse_rules(tip_text)
ev = tipcheck.evaluate(rule, ws, p.cfg())
kind, title, detail = ev["verdict"]
verdict = ui.verdict_html(kind, title, detail, rule.red_flags)
rule_txt = html.escape(rule.describe()[0].upper() + rule.describe()[1:])

# morning message on the phone
morning, _ = notify.build_morning(ws, rows, facts, use_ai=False)
phone = ui.phone_html("".join(f'<div class="ln">{ln or "&nbsp;"}</div>' for ln in morning.split("\n")), "GoldLens Bot", "08:30")
phone = phone.replace("<br>", "")

# logo variants
logo = ui.LOGO_IMG
logo_big = logo.replace('class="" style="width:38px;height:38px"', 'class="logo" style="width:120px;height:120px"')
logo_lock = logo.replace('style="width:38px;height:38px"', 'style="width:150px;height:150px"')

title_words = " ".join(
    f'<span class="w{" goldtxt" if w in ("TinyFish.",) else ""}">{html.escape(w)}</span>'
    for w in "Hack in Hills, powered by TinyFish.".split())

# audio
v = lambda t: round(t, 2)
vo8_end = scenes[7]["vo"] + durs[7]
lane = {"version": 1, "lanes": [{"target": "volume", "points": [
    {"t": 0, "v": 0}, {"t": 1.0, "v": 0.15}, {"t": v(vo8_end), "v": 0.15}, {"t": v(vo8_end + 0.5), "v": 0.34},
    {"t": v(TOTAL - 1.4), "v": 0.34}, {"t": TOTAL, "v": 0}]}]}
vo_tags = "\n".join(
    f'  <audio id="vo{i + 1}" src="assets/vo/vo{i + 1}.wav" data-start="{s["vo"]}" data-duration="{s["vodur"]:.2f}" '
    f'data-track-index="3" data-volume="1"></audio>' for i, s in enumerate(scenes))
sfx = [("bell1", "impactBell_heavy_000.ogg", K["wordmark"], 0.45),
       ("card1", "drop_001.ogg", K["cards"][0] - 0.03, 0.42), ("card4", "drop_002.ogg", K["cards"][3] - 0.03, 0.42),
       ("merge", "impactSoft_medium_001.ogg", K["morph"], 0.55),
       ("scan1", "drop_001.ogg", K["scan"][0] - 0.03, 0.4),
       ("stamp", "impactSoft_heavy_001.ogg", K["stamp"] - 0.02, 0.75),
       ("ping", "impactGlass_light_002.ogg", S[6] + 0.7, 0.5),
       ("bell2", "impactBell_heavy_000.ogg", S[7] + 0.25, 0.5)]
def media_len(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout
    return min(float(out.strip()), 1.5)


sfx_tags = "\n".join(
    f'  <audio id="sfx-{name}" src="assets/sfx/{f}" data-start="{t:.2f}" '
    f'data-duration="{media_len(OUT / "assets" / "sfx" / f):.2f}" '
    f'data-track-index="{11 + j}" data-volume="{vol}"></audio>' for j, (name, f, t, vol) in enumerate(sfx))

css = ui.CSS.replace("<style>", "").replace("</style>", "")
css = re.sub(r"@import url\([^)]*\);", "", css)

timing = {"total": TOTAL, "s": S, "scenes": [{"id": s["id"], "start": s["start"], "dur": s["dur"]} for s in scenes],
          "k": K, "nets": nets, "tip": tip_text}

tpl = (ROOT / "brag-output" / "work" / "template.html").read_text(encoding="utf-8")
fills = {
    "__COMPONENT_CSS__": css, "__TOTAL__": f"{TOTAL}", "__S1__": f"{S[0]}", "__S2__": f"{S[1]}",
    "__BRAND_DUR__": f"{round(S[7] - S[1], 2)}",
    **{f"__S{i + 1}__": f"{S[i]}" for i in range(8)}, **{f"__D{i + 1}__": f"{scenes[i]['dur']}" for i in range(8)},
    "__LOGO__": logo, "__LOGO_BIG__": logo_big, "__LOGO_LOCK__": logo_lock, "__TITLE_WORDS__": title_words,
    "__CARDS__": "".join(cards), "__CHART__": chart, "__LEGEND__": legend,
    "__SCANNER__": ui.scanner_cards_html(rows[:3], p.entry_z),
    "__C0__": f"₹{nets[0] / 1e5:.2f} lakh", "__C1__": f"₹{nets[1] / 1e5:.2f} lakh",
    "__C2__": ("−" if nets[2] < 0 else "") + f"₹{abs(nets[2]):,.0f}",
    "__RULE__": rule_txt, "__VERDICT__": verdict,
    "__CLAIM__": f"{rule.claimed_annual_pct:.0f}%", "__NAIVE__": f"{ev['naive']['ann_pct']:+.1f}%".replace("-", "−"),
    "__HONEST__": f"{ev['honest']['ann_pct']:+.1f}%".replace("-", "−"),
    "__PHONE__": phone, "__MUSIC_LANE__": json.dumps(lane), "__VO_TAGS__": vo_tags, "__SFX_TAGS__": sfx_tags,
    "__TIMING__": json.dumps(timing, ensure_ascii=False), "__PATHS__": json.dumps(paths),
}
for k in sorted(fills, key=len, reverse=True):
    tpl = tpl.replace(k, fills[k])
left = re.findall(r"__[A-Z0-9_]+__", tpl)
assert not left, left
(OUT / "index.html").write_text(tpl, encoding="utf-8")
print(f"total {TOTAL}s; scenes:", [(s["id"], s["start"], s["dur"]) for s in scenes])
print("keys:", K)
print("nets:", nets, "| tip verdict:", title, "| naive", ev["naive"]["ann_pct"], "honest", ev["honest"]["ann_pct"])
