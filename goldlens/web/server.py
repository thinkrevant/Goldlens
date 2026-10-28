"""GoldLens website: landing page at /, the full dashboard at /app, JSON-free htmx endpoints under /api."""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import notify, telegram, ui
from ..config import ROOT
from ..sitedata import build_site_data
from . import pages, state
from .state import COOKIE, Params

STATIC = Path(__file__).parent / "static"
SITE = ROOT / "site"

notify.load_env()
app = FastAPI(title="GoldLens", docs_url=None, redoc_url=None)


def params(request: Request) -> Params:
    return Params.from_cookie(request.cookies.get(COOKIE))


def is_local(request: Request) -> bool:
    """Writing settings to .env is only allowed from the machine running GoldLens, never through a proxy."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient") and "x-forwarded-for" not in request.headers


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


# ---------------------------------------------------------------- landing page
@app.get("/")
def landing():
    return FileResponse(SITE / "index.html")


@app.get("/data.js")
def site_data(request: Request):
    p = params(request)
    data = build_site_data(state.workspace(p.roll_bdays))
    body = "window.GOLDLENS = " + json.dumps(data, ensure_ascii=False, default=str) + ";\n"
    return Response(body, media_type="application/javascript", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- app shell + pages
@app.get("/app")
def app_root():
    return RedirectResponse("/app/overview")


@app.get("/app/static/components.css")
def components_css():
    css = ui.CSS.replace("<style>", "").replace("</style>", "")
    return Response(css, media_type="text/css")


@app.get("/app/static/plotly.min.js")
def plotly_js():
    """Plotly.js bundled with the Python plotly package: no CDN, and always the version the figures were built with."""
    from plotly.offline import get_plotlyjs
    return Response(get_plotlyjs(), media_type="application/javascript", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/app/{page}", response_class=HTMLResponse)
def page(page: str, request: Request):
    if page not in pages.PAGES:
        return RedirectResponse("/app/overview")
    p, local = params(request), is_local(request)
    body = pages.alerts(p, local) if page == "alerts" else pages.RENDER[page](p)
    if is_htmx(request) and not request.headers.get("hx-history-restore-request"):
        return HTMLResponse(body, headers={"HX-Trigger": json.dumps({"pageChanged": page})})
    return HTMLResponse(pages.shell(p, page, body, local))


@app.post("/app/settings")
async def save_settings(request: Request):
    form = dict(await request.form())
    form.setdefault("fees_on", "off")
    p = Params.parse(form)
    resp = Response(status_code=204, headers={"HX-Refresh": "true"})
    resp.set_cookie(COOKIE, p.to_cookie(), max_age=60 * 60 * 24 * 180, samesite="lax", httponly=True)
    return resp


# ---------------------------------------------------------------- fragments
@app.get("/app/frag/normalise", response_class=HTMLResponse)
def frag_normalise(request: Request, mode: str = "px10"):
    return pages.frag_normalise(params(request), mode)


@app.get("/app/frag/pair", response_class=HTMLResponse)
def frag_pair(request: Request, pair: str = ""):
    return pages.frag_pair(params(request), pair)


@app.get("/app/frag/curve", response_class=HTMLResponse)
def frag_curve(request: Request, d: int = 0):
    return pages.frag_curve(params(request), d)


@app.get("/app/frag/rolldown", response_class=HTMLResponse)
def frag_rolldown(request: Request, s: int = 0, tau: int = 60):
    return pages.frag_rolldown(params(request), s, tau)


@app.get("/app/frag/custom", response_class=HTMLResponse)
def frag_custom(request: Request):
    return pages.frag_custom(params(request), pages.flags_from(dict(request.query_params)))


@app.get("/app/frag/live", response_class=HTMLResponse)
def frag_live(request: Request):
    return pages.frag_live(params(request))


# ---------------------------------------------------------------- actions
@app.post("/api/brief", response_class=HTMLResponse)
def api_brief(request: Request):
    return pages.api_brief(params(request))


@app.post("/api/explain", response_class=HTMLResponse)
def api_explain(request: Request, pair: str = ""):
    return pages.api_explain(params(request), pair)


@app.post("/api/ask", response_class=HTMLResponse)
def api_ask(request: Request, q: str = Form("")):
    return pages.api_ask(params(request), q)


@app.post("/api/tip", response_class=HTMLResponse)
def api_tip(request: Request, tip: str = Form("")):
    return pages.api_tip(params(request), tip[:2000])


@app.post("/api/tip/eval", response_class=HTMLResponse)
async def api_tip_eval(request: Request):
    form = dict(await request.form())
    return pages.tip_verdict(params(request), pages.rule_from_form(form))


@app.post("/api/telegram/connect", response_class=HTMLResponse)
def tg_connect(request: Request, token: str = Form("")):
    p = params(request)
    if not is_local(request):
        return pages.alerts_body(p, False, (False, "Connecting a bot is only available on the computer running GoldLens."))
    ok, msg = notify.connect(token)
    return pages.alerts_body(p, True, (ok, msg))


@app.post("/api/telegram/disconnect", response_class=HTMLResponse)
def tg_disconnect(request: Request):
    p = params(request)
    if is_local(request):
        notify.disconnect()
        return pages.alerts_body(p, True, (True, "Disconnected. The token was removed from .env."))
    return pages.alerts_body(p, False, (False, "Only available on the computer running GoldLens."))


@app.post("/api/telegram/send", response_class=HTMLResponse)
def tg_send(request: Request):
    p = params(request)
    ws = state.workspace(p.roll_bdays)
    rows, _, facts = state.today(p)
    try:
        flash = (True, notify.send_morning(ws, rows, facts, os.environ.get("TELEGRAM_LANGUAGE", "English")))
    except telegram.TelegramError as e:
        flash = (False, f"Telegram: {e}")
    return pages.alerts_body(p, is_local(request), flash)


@app.post("/api/telegram/test", response_class=HTMLResponse)
def tg_test(request: Request):
    try:
        telegram.send("🪙 <b>GoldLens test</b>\nTelegram alerts are working.")
        flash = (True, "Test message sent.")
    except telegram.TelegramError as e:
        flash = (False, f"Telegram: {e}")
    return pages.alerts_body(params(request), is_local(request), flash)


@app.post("/api/telegram/lang", response_class=HTMLResponse)
def tg_lang(request: Request, when: str = Form("08:30"), lang: str = Form("")):
    local = is_local(request)
    if local and lang in ("English", "Hindi") and lang != os.environ.get("TELEGRAM_LANGUAGE", "English"):
        notify.set_env_value("TELEGRAM_LANGUAGE", lang)
        os.environ["TELEGRAM_LANGUAGE"] = lang
    when = when if re.fullmatch(r"\d{2}:\d{2}", when or "") else "08:30"
    return pages.alerts_body(params(request), local, None, when)


@app.post("/api/telegram/preview-ai", response_class=HTMLResponse)
def tg_preview_ai(request: Request):
    from .. import ai
    p = params(request)
    _, _, facts = state.today(p)
    ai.complete("morning", facts, os.environ.get("TELEGRAM_LANGUAGE", "English"))
    return pages.alerts_body(p, is_local(request))


@app.get("/api/trades.csv")
def trades_csv(request: Request):
    import pandas as pd
    p = params(request)
    q = dict(request.query_params)
    flags = tuple((k, q.get(k) == "1") for k, _ in pages.FLAG_LABELS) if q else ()
    _, results, _ = state.custom(p, flags)
    tl = pd.concat([r.trades.assign(pair=f"{a}/{b}") for (a, b), r in results.items() if not r.trades.empty], ignore_index=True)
    return Response(tl.to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=goldlens_trades.csv"})


@app.get("/api/panel.csv")
def panel_csv(request: Request):
    df = state.workspace(params(request).roll_bdays).df
    return Response(df.to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=goldlens_panel.csv"})


@app.post("/api/refresh-data", response_class=PlainTextResponse)
def refresh_data(request: Request):
    """Download any new MCX days, then rebuild every cached result. Local only."""
    if not is_local(request):
        return PlainTextResponse("not allowed", status_code=403)
    msg = notify.refresh_data()
    state.clear()
    return msg


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


app.mount("/app/static", StaticFiles(directory=STATIC), name="static")
app.mount("/", StaticFiles(directory=SITE), name="site")
