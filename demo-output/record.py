"""Record the real GoldLens app frame by frame: deterministic cursor, typing, scrolling and CSS animations,
captured at 2880x1620 (1.5x) so the edit can zoom in without blur. One mp4 per feature clip."""
import base64
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).parent / "rec"
FPS = 30
TIP = ("Buy GOLDPETAL when it's 1% cheaper than GOLDM, sell when it comes back to normal. "
       "Easy 40% a year, guaranteed! Join my VIP Telegram")

INIT = r"""
(() => {
  const css = `html{scroll-behavior:auto!important} ::-webkit-scrollbar{display:none} html{scrollbar-width:none}
    #__cur{position:fixed;left:0;top:0;width:30px;height:30px;z-index:2147483647;pointer-events:none;transform-origin:3px 2px;
      filter:drop-shadow(0 2px 4px rgba(0,0,0,.55))}
    #__rip{position:fixed;left:0;top:0;width:64px;height:64px;margin:-32px 0 0 -32px;border-radius:50%;z-index:2147483646;
      pointer-events:none;border:3px solid #F6D98B;opacity:0;box-sizing:border-box}`;
  const add = () => {
    if (document.getElementById('__cur')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M3 2 L3 19 L7.5 14.8 L10.6 21.6 L13.6 20.3 L10.6 13.6 L16.8 13.6 Z" fill="#fff" stroke="#0B0F17" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    const r = document.createElement('div'); r.id = '__rip';
    document.body.appendChild(r); document.body.appendChild(c);
  };
  window.__frame = (ms, x, y, rip, press, sy) => {
    add();
    if (sy !== null) window.scrollTo(0, sy);
    for (const a of document.getAnimations()) {
      if (a.__base === undefined) a.__base = (a.currentTime || 0) - ms;
      a.pause(); a.currentTime = Math.max(0, a.__base + ms);
    }
    const c = document.getElementById('__cur');
    c.style.transform = `translate(${x - 3}px, ${y - 2}px) scale(${press ? 0.86 : 1})`;
    const r = document.getElementById('__rip');
    if (rip > 0 && rip < 1) {
      r.style.left = x + 'px'; r.style.top = y + 'px';
      r.style.transform = `scale(${0.3 + rip * 1.1})`; r.style.opacity = String(0.85 * (1 - rip));
    } else r.style.opacity = '0';
  };
  if (document.readyState !== 'loading') add(); else document.addEventListener('DOMContentLoaded', add);
})();
"""


def ease(t):
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Clip:
    def __init__(self, rec, name):
        self.rec, self.name, self.dir = rec, name, OUT / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.n = 0

    @property
    def t(self):
        return self.n / FPS

    def frame(self, rip=0.0, press=False, sy=None):
        r = self.rec
        r.ms += 1000 / FPS
        r.page.evaluate("([ms,x,y,rip,press,sy]) => window.__frame(ms,x,y,rip,press,sy)", [r.ms, r.x, r.y, rip, press, sy])
        data = r.cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 90, "optimizeForSpeed": True})["data"]
        (self.dir / f"f{self.n:05d}.jpg").write_bytes(base64.b64decode(data))
        self.n += 1

    def until(self, t, **kw):
        while self.t < t - 1e-6:
            self.frame(**kw)

    def move(self, x, y, t_end):
        r = self.rec
        x0, y0, n = r.x, r.y, max(1, round((t_end - self.t) * FPS))
        for i in range(1, n + 1):
            k = ease(i / n)
            r.x, r.y = x0 + (x - x0) * k, y0 + (y - y0) * k
            r.page.mouse.move(r.x, r.y)
            self.frame()

    def scroll(self, y1, t_end, to=None):
        r = self.rec
        y0 = r.page.evaluate("window.scrollY")
        x0, cy0, n = r.x, r.y, max(1, round((t_end - self.t) * FPS))
        for i in range(1, n + 1):
            k = ease(i / n)
            if to:
                r.x, r.y = x0 + (to[0] - x0) * k, cy0 + (to[1] - cy0) * k
            self.frame(sy=y0 + (y1 - y0) * k)

    def tap(self, real=None, dur=0.35):
        """Visual click: press + ripple. `real` is called at the press moment to do the actual click."""
        n = round(dur * FPS)
        for i in range(n):
            if i == 2 and real:
                real()
            self.frame(rip=(i + 1) / n, press=i < 4)

    def type(self, text, t_end):
        n = max(1, round((t_end - self.t) * FPS))
        done = 0
        for i in range(1, n + 1):
            upto = round(len(text) * i / n)
            if upto > done:
                self.rec.page.keyboard.insert_text(text[done:upto])
                done = upto
            self.frame()

    def encode(self):
        out = OUT / f"{self.name}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(self.dir / "f%05d.jpg"),
                        "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
        print(f"{self.name}: {self.n} frames ({self.n / FPS:.2f}s) -> {out.name}", flush=True)


class Rec:
    def __init__(self, page, cdp):
        self.page, self.cdp, self.ms, self.x, self.y = page, cdp, 0.0, 1250.0, 520.0

    def nav(self, label, heading):
        """Real click on a sidebar item after its clip ended, then wait for the new page."""
        self.page.evaluate("window.scrollTo(0,0)")
        self.page.locator(f'.nav-i[data-page="{label}"]').click()
        self.page.get_by_text(heading, exact=False).first.wait_for(timeout=60000)
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1200)
        self.page.evaluate("window.scrollTo(0,0)")


def main(only=None):
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1.5)
        ctx.add_init_script(INIT)
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        r = Rec(page, cdp)

        # 1. landing page -> "Open the live app"
        page.goto(BASE + "/", wait_until="networkidle"); page.wait_for_timeout(4000)
        c = Clip(r, "c1_landing")
        c.until(0.5); c.move(468, 683, 2.0); c.until(2.8); c.tap(); c.until(4.2); c.encode()
        page.goto(BASE + "/app/overview", wait_until="networkidle"); page.wait_for_timeout(2500)

        # 2. overview
        c = Clip(r, "c2_overview")
        c.until(0.6); c.move(1475, 300, 1.8); c.until(3.4); c.move(575, 560, 4.6); c.until(5.9)
        c.move(1390, 640, 7.0); c.until(8.0); c.move(85, 227, 8.7); c.tap(); c.until(9.4); c.encode()
        r.nav("scanner", "Relative-value scanner")

        # 3. scanner
        c = Clip(r, "c3_scanner")
        c.until(0.4); c.move(388, 361, 1.5); c.until(2.8); c.move(488, 423, 3.8); c.until(4.8)
        c.scroll(520, 6.3, to=(900, 700)); c.until(7.9); c.move(86, 310, 8.6); c.tap(); c.until(9.2); c.encode()
        r.nav("backtest", "Where does a backtest")

        # 4. backtest honesty ladder
        c = Clip(r, "c4_backtest")
        c.until(0.4); c.move(900, 293, 1.4); c.until(2.4); c.move(1430, 489, 3.4); c.until(4.6)
        c.move(1450, 677, 5.6); c.until(7.4); c.move(98, 352, 8.1); c.tap(); c.until(8.8); c.encode()
        r.nav("tips", "A lie detector for trading tips")

        # 5. tip checker: type a real tip, check it, read the verdict
        c = Clip(r, "c5_tips")
        c.until(0.3); c.move(700, 330, 1.1)
        c.tap(real=lambda: page.locator("textarea[name=tip]").click())
        c.type(TIP, 4.7); c.move(337, 411, 5.4)

        def check():
            page.get_by_text("Check this tip").click()
            page.locator(".verdict").first.wait_for(timeout=60000)
            page.wait_for_load_state("networkidle"); page.wait_for_timeout(800)
        c.tap(real=check); c.until(6.2)
        c.scroll(420, 7.4, to=(1000, 760)); c.until(10.2); c.move(104, 476, 10.75); c.tap(); c.until(11.2); c.encode()
        r.nav("ask", "Ask GoldLens")

        # 6. ask the AI analyst
        c = Clip(r, "c6_ask")
        c.until(0.3); c.move(745, 238, 1.2)

        def ask():
            page.get_by_text("Is any alert worth the costs today?").first.click()
            page.get_by_text("No alert passes", exact=False).first.wait_for(timeout=120000)
            page.wait_for_load_state("networkidle"); page.wait_for_timeout(800)
        c.tap(real=ask); c.until(2.0); c.move(870, 450, 3.5); c.until(5.4); c.move(77, 185, 5.95); c.tap(); c.until(6.5); c.encode()
        r.nav("alerts", "Morning briefing on Telegram")

        # 7. alerts: Telegram morning brief
        c = Clip(r, "c7_alerts")
        c.until(0.3); c.move(624, 477, 1.4); c.until(2.4); c.move(1330, 520, 3.5); c.until(5.3); c.encode()
        b.close()


if __name__ == "__main__":
    main()
