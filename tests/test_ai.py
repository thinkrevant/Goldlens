import pytest

from goldlens import ai

FACTS = {"as_of": "2026-10-16", "market": {"spot_implied": 146152, "carry_pct": 11.14},
         "alerts": [{"status": "Normal"}], "backtest_honest": {"net_pnl": -3493, "costs": 257093, "trades": 181}}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "XAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(ai, "BRIEF_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ai, "_disabled", {})
    monkeypatch.setattr(ai, "last_used", None)


def _ok(*chunks):
    def gen(kind, facts, language, question):
        yield from chunks
    return gen


def _fail(note, lasting):
    calls = []

    def gen(kind, facts, language, question):
        calls.append(1)
        yield ai._Fail(note, lasting)
    gen.calls = calls
    return gen


def test_chain_order_follows_configured_keys(monkeypatch):
    assert ai.chain() == [] and not ai.has_key()
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setenv("XAI_API_KEY", "x")
    assert ai.chain() == ["grok", "openrouter"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert ai.chain() == ["claude", "grok", "openrouter"]


def test_no_key_gives_template():
    out = ai.complete("brief", FACTS)
    assert "Template brief" in out and "OPENROUTER_API_KEY" in out


def test_success_is_streamed_cached_and_labelled(monkeypatch, tmp_path):
    monkeypatch.setenv("XAI_API_KEY", "x")
    calls = []

    def gen(kind, facts, language, question):
        calls.append(1)
        yield "Gold is "
        yield "quiet today."
    monkeypatch.setattr(ai, "_stream_grok", gen)
    assert ai.complete("brief", FACTS) == "Gold is quiet today."
    assert ai.last_used == "Grok"
    assert ai.complete("brief", FACTS) == "Gold is quiet today."
    assert len(calls) == 1  # second call served from cache
    assert len(list(tmp_path.glob("brief-*.md"))) == 1


def test_no_credit_provider_falls_through_and_is_skipped_next_time(monkeypatch):
    """The real situation: an xAI key without credits plus an OpenRouter key."""
    monkeypatch.setenv("XAI_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    grok = _fail("xAI account has no credits or hit its spending limit", lasting=True)
    monkeypatch.setattr(ai, "_stream_grok", grok)
    monkeypatch.setattr(ai, "_stream_openrouter", _ok("Free model ", "answer."))
    assert ai.complete("brief", FACTS) == "Free model answer."
    assert ai.last_used.startswith("OpenRouter")
    assert ai.chain() == ["openrouter"]
    ai.complete("alert", {"pair": "GOLDTEN/GOLDGUINEA"})
    assert len(grok.calls) == 1  # never retried after a lasting failure


def test_temporary_failure_is_retried_later(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setattr(ai, "_stream_openrouter", _fail("OpenRouter rate limit reached, try again later", False))
    out = ai.complete("brief", FACTS)
    assert "rate limit" in out and "Template brief" in out
    assert ai.chain() == ["openrouter"]


def test_all_failures_show_template_and_are_not_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("XAI_API_KEY", "x")
    monkeypatch.setattr(ai, "_stream_grok", _fail("xAI account has no credits or hit its spending limit", True))
    out = ai.complete("brief", FACTS)
    assert "no credits" in out
    assert not list(tmp_path.glob("*.md"))


def test_cached_answer_remembers_its_author(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setattr(ai, "_stream_openrouter", _ok("Cached ", "brief."))
    assert ai.complete("brief", FACTS) == "Cached brief."
    monkeypatch.setattr(ai, "last_used", None)
    assert ai.complete("brief", FACTS) == "Cached brief."
    assert ai.last_used == "OpenRouter"
