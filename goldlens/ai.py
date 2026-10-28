"""AI analyst: an LLM explains numbers that GoldLens has already computed.

Providers, tried in this order when their key is set in .env:
  Claude      ANTHROPIC_API_KEY
  xAI Grok    XAI_API_KEY
  OpenRouter  OPENROUTER_API_KEY   (free models by default)

If one fails for a lasting reason (bad key, no credits) it is skipped for the rest of the
session and the next one is tried. The model never produces a number of its own: it gets a
JSON fact sheet and is told to use only those figures. If every provider fails, or none is
configured, a deterministic template brief is shown, so the dashboard always works.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Iterator

from .config import BRIEF_CACHE_DIR

MODEL = "claude-opus-5-5"
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-4.7"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Free models come and go; "openrouter/free" routes to whichever free model is available.
OPENROUTER_DEFAULT_MODELS = ["google/gemma-4-31b-it:free", "openrouter/free"]

SYSTEM = """You are GoldLens, an analyst for Indian commodity traders covering the four MCX \
gold futures: GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL.

You receive a JSON fact sheet computed by GoldLens. Rules:
- Use only numbers that appear in the fact sheet. Never estimate, extrapolate or invent figures, \
prices, dates or probabilities. If something is not in the facts, say it is not available.
- All prices are already normalised to rupees per 10 g of 999 gold. Spreads and premiums are in \
basis points (bps; 100 bps = 1%).
- Be honest about uncertainty. A z-score is a statistical flag, not a forecast. If the backtest \
shows no edge after costs, say so plainly.
- Write for a busy retail trader: short sentences, concrete, no hype, no financial advice. \
Never tell the reader to buy or sell; describe what the data shows.
- Format: short Markdown with bold labels. No tables unless asked."""

LANG_NOTE = {
    "English": "Write in English.",
    "Hindi": "Write in simple Hindi (Devanagari script). Keep contract names, numbers and "
             "terms like z-score and bps in English.",
}

TASKS = {
    "brief": "Write today's GoldLens daily brief in 150-220 words with these parts: "
             "**Market** (gold level and implied carry), **Relative value** (which contracts look "
             "rich or cheap and whether any alert passed the cost check), **Backtest reality check** "
             "(what the honest backtest says), **Watch** (one or two things to monitor).",
    "morning": "Write the AI take for a morning phone notification: 2 or 3 plain sentences, at most 55 words, "
               "on what stands out in today's numbers and what to watch. No headings, no bullet points, no bold.",
    "alert": "Explain this one alert in under 120 words: what is mispriced, by how much versus "
             "normal, why it might exist, whether the expected move covers round-trip costs, "
             "and what would make the signal wrong.",
}

LABELS = {"claude": "Claude", "grok": "Grok", "openrouter": "OpenRouter"}
KEYS = {"claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"), "grok": ("XAI_API_KEY",),
        "openrouter": ("OPENROUTER_API_KEY",)}

_disabled: dict[str, str] = {}      # provider -> reason, for lasting failures this session
last_used: str | None = None        # label of whoever wrote the most recent answer
_or_model_used: str | None = None   # which OpenRouter model answered last


@dataclass
class _Fail:
    """Yielded by a provider instead of text when it cannot answer."""
    note: str
    lasting: bool = False           # bad key / no credits: skip this provider from now on


def _configured(p: str) -> bool:
    return any(os.environ.get(k, "").strip() for k in KEYS[p])


def chain() -> list[str]:
    return [p for p in ("claude", "grok", "openrouter") if _configured(p) and p not in _disabled]


def provider() -> str | None:
    c = chain()
    return c[0] if c else None


def provider_label() -> str:
    return last_used or LABELS.get(provider(), "template")


def has_key() -> bool:
    return any(_configured(p) for p in KEYS)


def _cache_path(kind: str, facts: dict, language: str, extra: str = ""):
    blob = json.dumps({"k": kind, "f": facts, "l": language, "x": extra}, sort_keys=True, default=str)
    return BRIEF_CACHE_DIR / f"{kind}-{hashlib.sha256(blob.encode()).hexdigest()[:16]}.md"


def _prompt(kind: str, facts: dict, language: str, question: str = "") -> str:
    task = TASKS.get(kind) or (
        "Answer the trader's question using only the fact sheet. If the facts cannot answer it, "
        "say what is missing. Under 150 words.\n\nQuestion: " + question)
    return (f"<facts>\n{json.dumps(facts, indent=1, default=str)}\n</facts>\n\n"
            f"{task}\n\n{LANG_NOTE.get(language, LANG_NOTE['English'])}")


def stream(kind: str, facts: dict, language: str = "English", question: str = "") -> Iterator[str]:
    """Yield the answer as text chunks; cached answers and the template are yielded whole."""
    global last_used
    path = _cache_path(kind, facts, language, question)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if text.startswith("<!-- by: "):  # first line records who wrote it
            head, _, text = text.partition("\n")
            last_used = head[len("<!-- by: "):-len(" -->")]
        yield text
        return
    providers = chain()
    if not providers:
        yield template(kind, facts, language, note="; ".join(_disabled.values()))
        return
    notes = []
    for p in providers:
        parts, fail = [], None
        gen = {"claude": _stream_claude, "grok": _stream_grok, "openrouter": _stream_openrouter}[p]
        for chunk in gen(kind, facts, language, question):
            if isinstance(chunk, _Fail):
                fail = chunk
                break
            parts.append(chunk)
            yield chunk
        text = "".join(parts).strip()
        if fail is None and text:
            last_used = LABELS[p] + (f" · {_or_model_used}" if p == "openrouter" and _or_model_used else "")
            BRIEF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(f"<!-- by: {last_used} -->\n{text}", encoding="utf-8")
            return
        if parts:  # failed mid-answer: keep what was written, don't cache it
            yield "\n\n_(The answer was cut off.)_"
            return
        fail = fail or _Fail(f"{LABELS[p]} returned an empty answer")
        notes.append(fail.note)
        if fail.lasting:
            _disabled[p] = fail.note
    yield template(kind, facts, language, note="; ".join(notes))


def _stream_claude(kind, facts, language, question, system=None, user=None):
    import anthropic

    client = anthropic.Anthropic()
    try:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            # On a safety decline, the API re-runs the request on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system or SYSTEM,
            messages=[{"role": "user", "content": user or _prompt(kind, facts, language, question)}],
        ) as s:
            for text in s.text_stream:
                yield text
            final = s.get_final_message()
        if final.stop_reason == "refusal":
            yield _Fail("Claude declined this request")
    except anthropic.AuthenticationError:
        yield _Fail("Claude API key rejected", lasting=True)
    except anthropic.PermissionDeniedError:
        yield _Fail("Claude access denied", lasting=True)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        yield _Fail(f"Claude unavailable ({type(e).__name__})")


def _openai_failure(name: str, e) -> _Fail:
    import openai

    if isinstance(e, openai.AuthenticationError):
        return _Fail(f"{name} API key rejected", lasting=True)
    if isinstance(e, openai.PermissionDeniedError):
        msg = str(e).lower()
        if "credit" in msg or "spending" in msg:
            return _Fail(f"{name} account has no credits or hit its spending limit", lasting=True)
        return _Fail(f"{name} denied the request", lasting=True)
    if isinstance(e, openai.RateLimitError):
        return _Fail(f"{name} rate limit reached, try again later")
    if getattr(e, "status_code", None) == 402:
        return _Fail(f"{name} needs credits (402)", lasting=True)
    return _Fail(f"{name} unavailable ({type(e).__name__})")


def _stream_grok(kind, facts, language, question, system=None, user=None):
    """xAI Grok through its OpenAI-compatible Responses API."""
    import openai

    client = openai.OpenAI(api_key=os.environ["XAI_API_KEY"], base_url=XAI_BASE_URL, timeout=120)
    try:
        events = client.responses.create(
            model=os.environ.get("XAI_MODEL") or XAI_DEFAULT_MODEL,
            input=[{"role": "system", "content": system or SYSTEM},
                   {"role": "user", "content": user or _prompt(kind, facts, language, question)}],
            stream=True,
            store=False,
        )
        for ev in events:
            if ev.type == "response.output_text.delta":
                yield ev.delta
    except (openai.APIStatusError, openai.APIConnectionError) as e:
        yield _openai_failure("xAI", e)


def _stream_openrouter(kind, facts, language, question, system=None, user=None):
    """OpenRouter chat completions; tries each model in turn until one answers."""
    import openai

    global _or_model_used
    client = openai.OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=OPENROUTER_BASE_URL,
                           timeout=120)
    custom = (os.environ.get("OPENROUTER_MODEL") or "").strip()
    models = ([custom] if custom else []) + [m for m in OPENROUTER_DEFAULT_MODELS if m != custom]
    last = None
    for model in models:
        try:
            chunks = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system or SYSTEM},
                          {"role": "user", "content": user or _prompt(kind, facts, language, question)}],
                stream=True,
                extra_headers={"X-OpenRouter-Title": "GoldLens"},
            )
            started = False
            for ch in chunks:
                delta = ch.choices[0].delta.content if ch.choices else None
                if delta:
                    started = True
                    yield delta
            if started:
                _or_model_used = model
                return
            last = _Fail(f"OpenRouter model {model} returned nothing")
        except (openai.APIStatusError, openai.APIConnectionError) as e:
            last = _openai_failure("OpenRouter", e)
            if last.lasting:  # key or account problem: another model won't help
                break
    yield last or _Fail("OpenRouter returned nothing")


def cached(kind: str, facts: dict, language: str = "English", question: str = "") -> str | None:
    """A previously generated answer, without calling any provider."""
    path = _cache_path(kind, facts, language, question)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return text.partition("\n")[2] if text.startswith("<!-- by: ") else text


def ask_json(system: str, user: str) -> tuple[dict | None, str]:
    """One-off structured request through the provider chain. Returns (parsed JSON or None, provider label)."""
    path = BRIEF_CACHE_DIR / f"json-{hashlib.sha256((system + user).encode()).hexdigest()[:16]}.json"
    if path.exists():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            return blob["data"], blob["by"]
        except (ValueError, KeyError):
            pass
    gens = {"claude": _stream_claude, "grok": _stream_grok, "openrouter": _stream_openrouter}
    for p in chain():
        parts, fail = [], None
        for chunk in gens[p]("json", {}, "English", "", system=system, user=user):
            if isinstance(chunk, _Fail):
                fail = chunk
                break
            parts.append(chunk)
        if fail is not None:
            if fail.lasting:
                _disabled[p] = fail.note
            continue
        text = "".join(parts)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            continue
        by = LABELS[p] + (f" · {_or_model_used}" if p == "openrouter" and _or_model_used else "")
        BRIEF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"data": data, "by": by}), encoding="utf-8")
        return data, by
    return None, ""


def complete(kind: str, facts: dict, language: str = "English", question: str = "") -> str:
    return "".join(stream(kind, facts, language, question))


def _fmt_rs(x) -> str:
    try:
        return f"Rs {float(x):,.0f}"
    except (TypeError, ValueError):
        return str(x)


def template(kind: str, facts: dict, language: str = "English", note: str = "") -> str:
    """Deterministic fallback built straight from the fact sheet."""
    head = (f"_Template brief ({note or 'no AI key set'}). Set ANTHROPIC_API_KEY, XAI_API_KEY "
            "or OPENROUTER_API_KEY in .env for the AI analyst._\n\n")
    if kind == "alert":
        a = facts
        return head + (
            f"**{a.get('pair')}**: spread is {a.get('spread_bps', 0):+.1f} bps vs a 60-day mean of "
            f"{a.get('mean_bps', 0):+.1f} bps (z = {a.get('z', 0):+.2f}). "
            f"Expected reversion is worth about {_fmt_rs(a.get('edge_rs'))} per 200 g pair against "
            f"{_fmt_rs(a.get('round_trip_cost_rs'))} of round-trip costs, so it "
            f"{'passes' if a.get('passes_cost_check') else 'does not pass'} the cost check. "
            "It is wrong if the gap reflects a lasting change, such as delivery premiums or a "
            "liquidity shift, rather than noise.")
    if kind != "brief":
        return head + "The template mode can only produce the daily brief and alert notes."
    m, bt = facts.get("market", {}), facts.get("backtest_honest", {})
    alerts = facts.get("alerts", [])
    live = [a for a in alerts if a.get("passes_cost_check")]
    flagged = [a for a in alerts if a.get("status") == "Flagged, below cost"]
    prem = facts.get("premiums_bps", {})
    prem_txt = ", ".join(f"{k} {v:+.0f} bps" for k, v in prem.items() if v == v)
    lines = [
        f"**Market** ({facts.get('as_of')}): implied spot {_fmt_rs(m.get('spot_implied'))} per 10 g of 999 gold; "
        f"futures carry {m.get('carry_pct', 0):.2f}% a year.",
        f"**Relative value**: premiums vs GOLDM after carry: {prem_txt or 'n/a'}. "
        + (f"{len(live)} alert(s) clear the cost check: " + "; ".join(a['pair'] for a in live) + "."
           if live else
           f"{len(flagged)} pair(s) flagged statistically, but none clears round-trip costs. Quiet day."
           if flagged else "No pair is statistically unusual today. Quiet day."),
        f"**Backtest reality check**: honest walk-forward net P&L {_fmt_rs(bt.get('net_pnl'))} after "
        f"{_fmt_rs(bt.get('costs'))} of costs over {bt.get('trades', 0)} trades (Sharpe {bt.get('sharpe', 0):.2f}).",
        "**Watch**: whether flagged gaps close within their usual holding period, and volume in the "
        "smaller contracts before expiry.",
    ]
    return head + "\n\n".join(lines)
