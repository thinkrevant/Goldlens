"""Build the GoldLens prototype-demo composition: recorded app clips framed on a branded stage,
camera zoom keyframes per feature, feature labels, voiceover, ducked music and click sounds."""
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
COMP = HERE / "composition"
(COMP / "assets" / "rec").mkdir(parents=True, exist_ok=True)
shutil.copy(HERE.parent / "deck" / "logo.svg", COMP / "assets" / "logo.svg")
for f in (HERE / "rec").glob("c*.mp4"):
    shutil.copy(f, COMP / "assets" / "rec" / f.name)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)


F = (0.9, 960, 540)  # framed: the app window floating on the stage
# id, clip, start, duration, label number, label title, label sub, camera keys (t, dur, scale, cx, cy), clicks (local t)
SCENES = [
    ("c1", "c1_landing", 2.4, 4.0, "", "GoldLens website", "Story and live app in one place",
     [(0.3, 3.3, 1.18, 560, 640)], [2.8]),
    ("c2", "c2_overview", 6.4, 9.2, "01", "Overview", "Four contracts, one honest scale",
     [(0.9, 1.0, 1.4, 952, 292), (3.3, 1.0, 1.5, 690, 560), (5.8, 1.0, 1.45, 1390, 600), (7.8, 0.8, *F)], [8.7]),
    ("c3", "c3_scanner", 15.6, 9.0, "02", "Scanner", "Alerts only when costs are covered",
     [(0.3, 1.0, 1.75, 487, 370), (4.5, 1.2, 1.1, 950, 560), (7.5, 0.8, *F)], [8.6]),
    ("c4", "c4_backtest", 24.6, 8.6, "03", "Honesty test", "Every backtest flaw, removed",
     [(0.3, 1.0, 1.3, 955, 480), (2.2, 1.0, 1.75, 1250, 489), (4.4, 1.0, 1.75, 1250, 650), (6.9, 0.9, *F)], [8.1]),
    ("c5", "c5_tips", 33.2, 11.0, "04", "Tip Checker", "A lie detector for trading tips",
     [(0.2, 0.9, 1.5, 850, 330), (4.6, 0.7, 1.45, 760, 370), (5.6, 0.7, *F), (7.3, 1.0, 1.45, 950, 440),
      (8.9, 0.9, 1.8, 1126, 620), (10.1, 0.7, *F)], [1.1, 5.4, 10.75]),
    ("c6", "c6_ask", 44.2, 6.3, "05", "Ask GoldLens", "AI analyst grounded in today's facts",
     [(0.2, 0.8, 1.6, 760, 250), (1.7, 0.9, 1.35, 950, 420), (5.1, 0.7, *F)], [1.2, 5.95]),
    ("c7", "c7_alerts", 50.5, 5.1, "06", "Morning brief", "Telegram, in English or Hindi",
     [(0.3, 1.0, 1.45, 624, 420), (2.3, 1.1, 1.6, 1330, 560)], []),
]
TOTAL, OUTRO = 60.0, 55.6
VO = [0.5, 6.7, 15.9, 24.9, 33.5, 44.5, 50.8, 56.1]


def place(s, cx, cy):
    if s <= 1:
        return 960 - s * 960, 540 - s * 540
    x = min(0, max(1920 - 1920 * s, 960 - s * cx))
    y = min(0, max(1080 - 1080 * s, 540 - s * cy))
    return round(x, 1), round(y, 1)


cams, labels, tweens, clicks = [], [], [], []
for i, (cid, clip, st, d, num, title, sub, keys, taps) in enumerate(SCENES):
    assert dur(HERE / "rec" / f"{clip}.mp4") >= d, clip
    cams.append(f'<div class="cam" id="cam-{cid}"><video id="v-{cid}" class="clip" src="assets/rec/{clip}.mp4" muted '
                f'data-start="{st}" data-duration="{d}" data-track-index="1"></video></div>')
    numhtml = f'<span class="num">{num}</span>' if num else ""
    labels.append(f'<div class="lbl clip" id="lbl-{cid}" data-start="{st + 0.35}" data-duration="{round(d - 0.85, 2)}" data-track-index="4">'
                  f'<div class="lin">{numhtml}<div><div class="lt">{title}</div><div class="ls">{sub}</div></div></div></div>')
    x0, y0 = place(*F)
    tweens.append({"sel": f"#cam-{cid}", "t": st, "set": {"scale": F[0], "x": x0, "y": y0}})
    for (t, du, s, cx, cy) in keys:
        x, y = place(s, cx, cy)
        tweens.append({"sel": f"#cam-{cid}", "t": round(st + t, 3), "to": {"scale": s, "x": x, "y": y, "duration": du}})
    clicks += [round(st + t, 2) for t in taps]

vo_d = [dur(COMP / "assets" / "vo" / f"v{i + 1}.wav") for i in range(8)]
vo_tags = "\n".join(f'  <audio id="vo{i + 1}" src="assets/vo/v{i + 1}.wav" data-start="{t}" data-duration="{vo_d[i]:.2f}" '
                    f'data-track-index="3" data-volume="1"></audio>' for i, t in enumerate(VO))
click_d = min(dur(COMP / "assets" / "sfx" / "drop_001.ogg"), 1.0)
sfx_tags = "\n".join(f'  <audio id="click{j + 1}" src="assets/sfx/drop_001.ogg" data-start="{t:.2f}" data-duration="{click_d:.2f}" '
                     f'data-track-index="{11 + j}" data-volume="0.35"></audio>' for j, t in enumerate(clicks))
bell_d = min(dur(COMP / "assets" / "sfx" / "impactBell_heavy_000.ogg"), 1.5)
vo8_end = VO[7] + vo_d[7]
lane = {"version": 1, "lanes": [{"target": "volume", "points": [
    {"t": 0, "v": 0}, {"t": 0.8, "v": 0.14}, {"t": round(vo8_end, 2), "v": 0.14}, {"t": round(vo8_end + 0.4, 2), "v": 0.32},
    {"t": TOTAL - 1.2, "v": 0.32}, {"t": TOTAL, "v": 0}]}]}

FONTS = "\n".join(
    f'@font-face {{ font-family: "Inter"; src: url("assets/fonts/inter-latin-{w}-normal.woff2") format("woff2"); font-weight: {w}; }}'
    for w in (400, 500, 600, 700, 800, 900)) + "\n" + "\n".join(
    f'@font-face {{ font-family: "JetBrains Mono"; src: url("assets/fonts/jetbrains-mono-latin-{w}-normal.woff2") format("woff2"); font-weight: {w}; }}'
    for w in (400, 500, 600))

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1920, height=1080">
<script src="assets/js/gsap.min.js"></script>
<style>
{FONTS}
html, body {{ margin: 0; background: #07090F; }}
#root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #07090F; font-family: "Inter", sans-serif; color: #E9EBF0; }}
#stage {{ position: absolute; inset: 0; background:
  radial-gradient(900px 600px at 82% 8%, rgba(224,176,74,.16), transparent 60%),
  radial-gradient(800px 600px at 8% 100%, rgba(91,141,239,.12), transparent 60%), #07090F; }}
#stage .grid {{ position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
  linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px); background-size: 80px 80px; }}
.cam {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; transform-origin: 0 0; border-radius: 18px; overflow: hidden;
  box-shadow: 0 40px 120px rgba(0,0,0,.65), 0 0 0 1px rgba(255,255,255,.07); opacity: 0; }}
.cam video {{ display: block; width: 1920px; height: 1080px; object-fit: cover; }}
.lbl {{ position: absolute; left: 72px; bottom: 72px; }}
.lin {{ display: flex; align-items: center; gap: 18px; padding: 16px 28px 16px 18px; border-radius: 18px;
  background: rgba(10,13,20,.86); border: 1px solid rgba(224,176,74,.35); box-shadow: 0 20px 60px rgba(0,0,0,.5); }}
.num {{ font-family: "JetBrains Mono", monospace; font-weight: 600; font-size: 26px; color: #0B0F17; background: #E0B04A;
  border-radius: 12px; padding: 8px 12px; }}
.lt {{ font-size: 32px; font-weight: 800; letter-spacing: -.01em; }}
.ls {{ font-size: 22px; color: #AEB5C4; margin-top: 2px; font-weight: 500; }}
.card {{ position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; padding-left: 170px; }}
.card .logo {{ width: 120px; height: 120px; }}
.card .eyebrow {{ font-size: 26px; font-weight: 700; letter-spacing: .22em; text-transform: uppercase; color: #E0B04A; margin-top: 38px; }}
.card .word {{ font-size: 150px; font-weight: 900; letter-spacing: -.04em; line-height: 1; margin-top: 14px;
  color: #F6D98B; }}
.card .sub {{ font-size: 36px; color: #C9CED8; margin-top: 22px; font-weight: 500; }}
.card .meta {{ font-family: "JetBrains Mono", monospace; font-size: 22px; color: #8A93A6; letter-spacing: .12em; margin-top: 34px; text-transform: uppercase; }}
.card .team {{ font-size: 30px; font-weight: 600; color: #E9EBF0; margin-top: 34px; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="1920" data-height="1080">
  <div id="stage"><div class="grid"></div></div>
  {chr(10).join("  " + c for c in cams)}
  <section id="title" class="clip" data-start="0" data-duration="2.4" data-track-index="2"><div class="card tin">
    <img class="logo" src="assets/logo.svg" alt="">
    <div class="eyebrow">Working prototype</div>
    <div class="word">GoldLens</div>
    <div class="sub">The real app, running on real MCX data</div>
    <div class="meta">973 trading days · settlement 16 Oct 2026</div>
  </div></section>
  {chr(10).join("  " + l for l in labels)}
  <section id="outro" class="clip" data-start="{OUTRO}" data-duration="{round(TOTAL - OUTRO, 2)}" data-track-index="2"><div class="card oin">
    <img class="logo" src="assets/logo.svg" alt="">
    <div class="word" style="margin-top:30px">GoldLens</div>
    <div class="sub">Honest intelligence for gold traders.</div>
    <div class="team">Team TechFast · Revant Raj</div>
    <div class="meta">Hack in Hills '26, powered by TinyFish · PS 03</div>
  </div></section>
  <audio id="music" src="assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3" data-start="0" data-duration="{TOTAL}"
    data-track-index="10" data-volume="1" data-automation='{json.dumps(lane)}'></audio>
{vo_tags}
{sfx_tags}
  <audio id="bell" src="assets/sfx/impactBell_heavy_000.ogg" data-start="{OUTRO + 0.35}" data-duration="{bell_d:.2f}" data-track-index="30" data-volume="0.45"></audio>
</div>
<script>
const TW = {json.dumps(tweens)};
const S = {json.dumps([[s[0], s[2], s[3]] for s in SCENES])};
const tl = gsap.timeline({{ paused: true }});
TW.forEach((w) => {{
  if (w.set) tl.set(w.sel, {{ ...w.set, opacity: 1 }}, w.t);
  else tl.to(w.sel, {{ ...w.to, ease: "power3.inOut" }}, w.t);
}});
// title card in and out, first scene fades up from the stage
tl.fromTo("#title .tin > *", {{ y: 40, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.6, ease: "power3.out", stagger: 0.08 }}, 0.1);
tl.to("#title .tin", {{ opacity: 0, duration: 0.35, ease: "power2.in" }}, 2.05);
tl.fromTo("#cam-c1", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.45, ease: "power2.out" }}, 2.4);
// each new page lands with a small settle so the cut reads as navigation
S.slice(0, -1).forEach(([id, st, d]) => tl.set(`#cam-${{id}}`, {{ opacity: 0 }}, st + d));
S.slice(1).forEach(([id, st]) => tl.fromTo(`#v-${{id}}`, {{ opacity: 0.35 }}, {{ opacity: 1, duration: 0.25, ease: "power1.out" }}, st));
// feature labels slide in, then out before the next cut
S.forEach(([id, st, d]) => {{
  tl.fromTo(`#lbl-${{id}} .lin`, {{ x: -40, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.5, ease: "power3.out" }}, st + 0.4);
  tl.to(`#lbl-${{id}} .lin`, {{ x: -20, opacity: 0, duration: 0.3, ease: "power2.in" }}, st + d - 0.8);
}});
// last scene fades to the outro card
tl.to("#cam-c7", {{ opacity: 0, duration: 0.35, ease: "power2.in" }}, {OUTRO} - 0.35);
tl.fromTo("#outro .oin > *", {{ y: 40, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.6, ease: "power3.out", stagger: 0.1 }}, {OUTRO} + 0.1);
window.__timelines["main"] = tl;
</script>
</body>
</html>
"""
(COMP / "index.html").write_text(html, encoding="utf-8")
print("scenes", [(s[0], s[2], s[3]) for s in SCENES], "clicks", clicks)
