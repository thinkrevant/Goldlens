import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from goldlens.config import PANEL_PATH  # noqa: E402

if not PANEL_PATH.exists():
    pytest.skip("no cached MCX panel", allow_module_level=True)

from goldlens import ai, telegram  # noqa: E402
from goldlens.web import pages, server  # noqa: E402
from goldlens.web.state import Params  # noqa: E402

HX = {"HX-Request": "true"}


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda kind, facts, language="English", question="": "**Market** is calm.")
    monkeypatch.setattr(ai, "cached", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")


@pytest.mark.parametrize("page", sorted(pages.PAGES))
def test_every_page_full_and_fragment(client, page, monkeypatch):
    from goldlens import live
    monkeypatch.setattr(live, "get_token", lambda: None)
    full = client.get(f"/app/{page}")
    assert full.status_code == 200 and "<aside class=\"side\">" in full.text and "htmx" in full.text
    frag = client.get(f"/app/{page}", headers=HX)
    assert frag.status_code == 200 and "<aside" not in frag.text and "gl-sec" in frag.text


def test_landing_and_live_site_data(client):
    r = client.get("/")
    assert r.status_code == 200 and "One honest answer" in r.text and 'href="/app"' in r.text
    js = client.get("/data.js")
    assert js.status_code == 200 and js.text.startswith("window.GOLDLENS = ")
    data = json.loads(js.text[len("window.GOLDLENS = "):].rstrip().rstrip(";"))
    assert data["meta"]["trading_days"] > 900 and len(data["ladder"]) == 7
    assert client.get("/styles.css").status_code == 200 and client.get("/app/static/components.css").status_code == 200


def test_fragments(client):
    assert '"type":"scatter"' in client.get("/app/frag/normalise?mode=close").text.replace(" ", "")
    pair = client.get("/app/frag/pair?pair=GOLDTEN/GOLDGUINEA").text
    assert "plot" in pair and "Explain GOLDTEN/GOLDGUINEA" in pair
    assert "plot" in client.get("/app/frag/curve?d=5").text
    assert "plot" in client.get("/app/frag/rolldown?s=10&tau=60").text
    off = client.get("/app/frag/custom?_submitted=1&gram_matched=1&next_day_fill=1&rolling_stats=1&true_contracts=1")
    on = client.get("/app/frag/custom?_submitted=1&gram_matched=1&next_day_fill=1&rolling_stats=1&true_contracts=1&apply_costs=1&liquidity_filter=1")
    assert off.status_code == on.status_code == 200 and off.text != on.text  # switching costs off changes the result


def test_tip_checker_end_to_end(client):
    from goldlens import tipcheck
    r = client.post("/api/tip", data={"tip": tipcheck.EXAMPLES[0]})
    assert r.status_code == 200 and "verdict" in r.text and "tip-editor" in r.text
    ev = client.post("/api/tip/eval", data={"a": "GOLDTEN", "b": "GOLDGUINEA", "side": "both", "mode": "z", "entry": "2",
                                            "exit": "0", "hold": "15", "claim": "0", "source": "you", "flags": "[]"})
    assert ev.status_code == 200 and "verdict" in ev.text
    assert "out of scope" in client.post("/api/tip", data={"tip": "Buy Reliance at 2800"}).text


def test_settings_cookie_is_clamped(client):
    r = client.post("/app/settings", data={"window": "999", "entry_z": "2.5", "language": "Hindi"})
    assert r.status_code == 204 and r.headers.get("HX-Refresh") == "true"
    p = Params.from_cookie(r.cookies.get("goldlens"))
    assert p.window == 120 and p.entry_z == 2.5 and p.language == "Hindi" and p.fees_on is False
    assert Params.from_cookie("garbage") == Params()


def test_ai_endpoints_use_the_fact_sheet(client):
    assert "Market" in client.post("/api/brief").text
    assert "msg-a" in client.post("/api/ask", data={"q": "What is carry?"}).text
    assert client.post("/api/ask", data={"q": "   "}).text == ""


def test_downloads(client):
    t = client.get("/api/trades.csv")
    header = t.text.splitlines()[0].split(",")
    assert t.status_code == 200 and "entry_date" in header and "pair" in header and len(t.text.splitlines()) > 50
    assert client.get("/api/panel.csv").text.startswith("date,")


def test_telegram_settings_are_local_only(client, monkeypatch):
    called = []
    from goldlens import notify
    monkeypatch.setattr(notify, "connect", lambda token: called.append(token) or (False, "x"))
    remote = client.post("/api/telegram/connect", data={"token": "1:a"}, headers={"X-Forwarded-For": "8.8.8.8"})
    assert "only available on the computer running GoldLens" in remote.text and called == []
    local = client.post("/api/telegram/connect", data={"token": "1:a"})
    assert local.status_code == 200 and called == ["1:a"]
    assert client.post("/api/refresh-data", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 403
