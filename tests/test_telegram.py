import json

import pandas as pd
import pytest

from goldlens import notify, telegram

FACTS = {"as_of": "2026-10-16", "premiums_bps": {"GOLDTEN": 4.8, "GOLDGUINEA": 51.7, "GOLDPETAL": 51.5},
         "market": {"spot_implied": 146152, "carry_pct": 11.14, "spot_change_30d_pct": -4.16}}
ALERT = {"pair": "GOLDTEN/GOLDGUINEA", "status": "ALERT", "z": 2.41, "spread_bps": -61.2, "mean_bps": -48.0,
         "edge_rs": 3900, "round_trip_cost_rs": 1300, "rich": "GOLDTEN", "cheap": "GOLDGUINEA",
         "leg_a": "GOLDTEN 30OCT26", "leg_b": "GOLDGUINEA 30OCT26"}
NORMAL = {**ALERT, "pair": "GOLDM/GOLDTEN", "status": "Normal", "z": -0.4}
CTX = {"today": pd.Timestamp("2026-10-20"), "spot_dd": 0.19,
       "events": [{"expiry": pd.Timestamp("2026-10-30"), "symbols": ["GOLDGUINEA", "GOLDPETAL", "GOLDTEN"],
                   "roll_out": pd.Timestamp("2026-10-23")}],
       "nearest": NORMAL}
TOKEN = "123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def __call__(self, token, method, **params):
        self.sent.append((method, params))
        return {"message_id": len(self.sent)}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakeTelegram()
    monkeypatch.setattr(telegram, "_call", f)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(notify, "STATE_PATH", tmp_path / "state.json")
    return f


def test_md_to_html_escapes_and_formats():
    out = telegram.md_to_html("**Market**: spread < 5 bps & rising\n- item one\n_note_")
    assert "<b>Market</b>" in out and "&lt; 5 bps &amp;" in out
    assert "• item one" in out and "<i>note</i>" in out


def test_split_respects_limit():
    text = "\n\n".join(["x" * 3000, "y" * 3000, "z" * 100])
    parts = telegram.split(text)
    assert len(parts) == 2 and all(len(p) <= telegram.MAX_LEN for p in parts)


def test_mask_hides_the_secret():
    assert telegram.mask(TOKEN) == "123456789:••••xxxx" and TOKEN[12:30] not in telegram.mask(TOKEN)


def test_morning_message_quiet_day():
    msg = telegram.morning_message(FACTS, CTX, "Gold is calm; watch the PETAL premium.", [NORMAL])
    for part in ("Morning brief", "Tue 20 Oct 2026", "settlement 16 Oct", "₹146,152", "▲0.19% d/d",
                 "No signal today", "Closest: GOLDM/GOLDTEN", "PETAL +52", "expire Fri 30 Oct (10 d)",
                 "rolls out 23 Oct", "AI take", "not investment advice"):
        assert part in msg, part
    assert len(msg) < telegram.MAX_LEN


def test_morning_message_with_signal_and_no_ai():
    msg = telegram.morning_message(FACTS, CTX, None, [ALERT, NORMAL])
    assert "1 signal today" in msg and "GOLDTEN/GOLDGUINEA" in msg and "₹3,900" in msg
    assert "AI take" not in msg


def _stub_pipeline(monkeypatch, rows):
    import goldlens.pipeline as pipeline
    from goldlens import ai
    monkeypatch.setattr(pipeline, "build_workspace", lambda: object())
    monkeypatch.setattr(pipeline, "daily_facts", lambda ws: (rows, {}, FACTS))
    monkeypatch.setattr(notify, "morning_context", lambda ws, rows, today=None: CTX)
    monkeypatch.setattr(ai, "complete", lambda kind, facts, lang: "Gold is calm.")


def test_one_message_per_morning_including_alerts(fake, monkeypatch):
    _stub_pipeline(monkeypatch, [ALERT, NORMAL])
    first = notify.run("English", refresh=False)
    assert len(fake.sent) == 1 and "morning message" in first
    assert "GOLDTEN/GOLDGUINEA" in fake.sent[0][1]["text"]  # the alert is inside the one message
    notify.run("English", refresh=False)
    notify.run("English", alerts_only=True, refresh=False)
    assert len(fake.sent) == 1  # no repeat, and the alert isn't sent again on its own
    state = json.loads(notify.STATE_PATH.read_text())
    assert state["daily"] == ["2026-10-16"] and state["alerts"] == ["2026-10-16|GOLDTEN/GOLDGUINEA"]


def test_alerts_only_sends_new_alerts_once(fake, monkeypatch):
    _stub_pipeline(monkeypatch, [ALERT])
    notify.run("English", alerts_only=True, refresh=False)
    notify.run("English", alerts_only=True, refresh=False)
    assert len(fake.sent) == 1 and "GoldLens alert" in fake.sent[0][1]["text"]


@pytest.fixture
def env_file(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\nTELEGRAM_BOT_TOKEN=\n")
    monkeypatch.setattr(notify, "ENV_PATH", env)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    return env


def test_connect_rejects_malformed_token(env_file):
    ok, msg = notify.connect("not-a-token")
    assert not ok and "doesn't look like a bot token" in msg


def test_connect_asks_to_press_start(env_file, monkeypatch):
    monkeypatch.setattr(telegram, "get_me", lambda t: {"username": "goldlens_demo_bot"})
    monkeypatch.setattr(telegram, "find_chat_id", lambda t: None)
    ok, msg = notify.connect(TOKEN)
    assert not ok and "press Start" in msg and "t.me/goldlens_demo_bot" in msg
    assert f"TELEGRAM_BOT_TOKEN={TOKEN}" in env_file.read_text()  # token kept for the second click


def test_connect_saves_and_says_hello(env_file, monkeypatch):
    monkeypatch.setattr(telegram, "get_me", lambda t: {"username": "goldlens_demo_bot"})
    monkeypatch.setattr(telegram, "find_chat_id", lambda t: ("987", "Revant"))
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text, token=None, chat_id=None: sent.append(chat_id) or 1)
    ok, msg = notify.connect(TOKEN)
    assert ok and "Revant" in msg and sent == ["987"]
    text = env_file.read_text()
    assert f"TELEGRAM_BOT_TOKEN={TOKEN}" in text and "TELEGRAM_CHAT_ID=987" in text and "OTHER=1" in text
    notify.disconnect()
    assert "TELEGRAM_BOT_TOKEN=\n" in env_file.read_text() and "TELEGRAM_CHAT_ID=\n" in env_file.read_text()


def test_send_requires_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(telegram.TelegramError):
        telegram.send("hi")
