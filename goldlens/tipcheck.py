"""Tip Checker: does a trading tip survive an honest backtest?

A tip in plain language ("buy GOLDPETAL when it's 1% cheaper than GOLDM, 40% a year!") is turned
into a precise rule: by the AI provider chain when one is available, by a built-in pattern reader
otherwise. The rule is replayed through the same honesty ladder as the main backtest: first the
way a tipster usually tests it, then with each flaw removed. The verdict shows the honest return
next to the claim, and how much of the "edge" each flaw created.

Scope: rules about the price gap between two MCX gold contracts. Anything else is reported as
out of scope rather than guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .analytics import pair_frame
from .backtest import BacktestConfig, attribution, ladder_configs, run_pair
from .config import LEG_GRAMS, SPECS, SYMBOLS

ALIASES = [
    (r"gold\s*petal|goldpetal|\bpetal\b", "GOLDPETAL"),
    (r"gold\s*guinea|goldguinea|\bguinea\b", "GOLDGUINEA"),
    (r"gold\s*ten\b|goldten|gold\s*10\s*g?\b", "GOLDTEN"),
    (r"gold\s*mini|goldm\b|gold\s*m\b|\bmini\b", "GOLDM"),
]

REASONS = {
    "+ gram-matched sizing": "Hidden gold bet (1 lot vs 1 lot)",
    "+ fill next day": "Trading at a price you couldn't get",
    "+ past-only z-score": "Peeking at future data",
    "+ real contracts & carry": "Fake jumps at expiry, ignored carry",
    "+ costs": "Brokerage, taxes and slippage",
    "+ liquidity filter (honest)": "Trading on stale prices",
}


@dataclass
class Rule:
    buy_leg: str                    # leg A: bought when cheap (or sold when rich, for short_a)
    other_leg: str                  # leg B
    side: str = "long_a"            # long_a | short_a | both
    mode: str = "level"             # level: thresholds in bps of the price gap; z: in standard deviations
    entry: float = 100.0
    exit: float = 0.0
    max_hold: int = 20
    claimed_annual_pct: float | None = None
    source: str = "pattern reader"
    notes: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)

    def describe(self) -> str:
        unit = "bps" if self.mode == "level" else "σ"
        a, b = self.buy_leg, self.other_leg
        when = {"long_a": f"buy {a} / sell {b} when {a} is {self.entry:g} {unit} cheaper",
                "short_a": f"sell {a} / buy {b} when {a} is {self.entry:g} {unit} richer",
                "both": f"trade {a} vs {b} whenever the gap passes ±{self.entry:g} {unit}"}[self.side]
        exit_txt = "back to parity" if self.exit == 0 and self.mode == "level" else (
            "back to its mean" if self.exit == 0 else f"within {self.exit:g} {unit}")
        return f"{when}; exit when the gap is {exit_txt}, or after {self.max_hold} days."


# ---------------------------------------------------------------- parsing
def _contracts(text: str) -> list[str]:
    hits = []
    for pat, sym in ALIASES:
        for m in re.finditer(pat, text, flags=re.I):
            hits.append((m.start(), m.end(), sym))
    hits.sort()
    out, last_end = [], -1
    for s, e, sym in hits:
        if s >= last_end and sym not in out:
            out.append(sym)
        last_end = max(last_end, e)
    return out


def _sym_before(verbs: str, text: str) -> str | None:
    m = re.search(rf"([a-z0-9 ]{{2,24}}?)\s+(?:{verbs})\b", text, flags=re.I)
    if not m:
        return None
    found = _contracts(m.group(1))
    return found[-1] if found else None


def _sym_after(verb: str, text: str) -> str | None:
    m = re.search(rf"\b{verb}\s+(?:the\s+|a\s+)?([a-z0-9 ]{{2,14}})", text, flags=re.I)
    if not m:
        return None
    found = _contracts(m.group(1))
    return found[0] if found else None


def parse_rules(text: str) -> Rule | None:
    """Deterministic pattern reader for the common shapes of gold relative-value tips."""
    t = " ".join(text.split())
    legs = _contracts(t)
    if not legs:
        return None
    notes = []
    buy = _sym_after("buy", t) or _sym_after("long", t) or _sym_before(r"le\s*lo|lelo|khareed\w*|kharid\w*", t)
    sell = _sym_after("sell", t) or _sym_after("short", t) or _sym_before(r"bech\s*do|becho|bech", t)
    if buy and sell and buy != sell:
        a, b, side = buy, sell, "long_a"
    elif buy:
        a, side = buy, "long_a"
        b = next((x for x in legs if x != a), None)
    elif sell:
        a, side = sell, "short_a"
        b = next((x for x in legs if x != a), None)
    else:
        a, side = legs[0], "both"
        b = legs[1] if len(legs) > 1 else None
    if b is None:
        b = "GOLDM" if a != "GOLDM" else "GOLDTEN"
        notes.append(f"No second contract named; compared against {b}.")
    if re.search(r"both ways|either (way|side)|whichever", t, flags=re.I):
        side = "both"

    # claimed return: a % followed by a time unit
    claimed = None
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:returns?|profit|gains?)?\s*(?:a|per|every|har|/)?\s*"
                         r"(year|annum|annual|yearly|cagr|saal|month|monthly|mahina|mahine|week|weekly|hafta|hafte)",
                         t, flags=re.I):
        val, unit = float(m.group(1)), m.group(2).lower()
        claimed = val * (12 if unit.startswith(("month", "mahin")) else 52 if unit.startswith(("week", "haft")) else 1)
    claim_spans = [m.span() for m in re.finditer(r"\d+(?:\.\d+)?\s*%\s*(?:returns?|profit|gains?)?\s*(?:a|per|every|har|/)?\s*"
                                                  r"(?:year|annum|annual|yearly|cagr|saal|month|monthly|mahina|mahine|week|weekly|hafta|hafte)",
                                                  t, flags=re.I)]

    mode, entry = "level", None
    z = re.search(r"(\d+(?:\.\d+)?)\s*(?:σ|sigma|sd\b|std|standard deviations?|z\b)", t, flags=re.I)
    bps = re.search(r"(\d+(?:\.\d+)?)\s*(?:bps|bp\b|basis points?)", t, flags=re.I)
    if z:
        mode, entry = "z", float(z.group(1))
    elif bps:
        entry = float(bps.group(1))
    else:
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", t):
            if not any(s <= m.start() < e for s, e in claim_spans):
                entry = float(m.group(1)) * 100
                break
    if entry is None:
        entry = 2.0 if mode == "z" else 100.0
        notes.append(f"No threshold given; assumed {entry:g} {'σ' if mode == 'z' else 'bps'}.")

    exit_ = 0.0
    if re.search(r"\bhal(f|ves|ved)\b", t, flags=re.I):
        exit_ = entry / 2
    hold = 20
    h = re.search(r"(\d+)\s*(?:trading\s*)?(day|days|week|weeks)\b", t, flags=re.I)
    if h:
        hold = int(h.group(1)) * (5 if h.group(2).lower().startswith("week") else 1)

    rule = Rule(a, b, side, mode, entry, exit_, max(1, min(hold, 120)), claimed, "pattern reader", notes)
    rule.red_flags = red_flags(t, rule)
    return rule


AI_SYSTEM = """You convert a trading tip about MCX gold futures into a strict JSON rule.
Contracts: GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL. Return ONLY a JSON object, no prose:
{"in_scope": true|false, "buy_leg": "...", "other_leg": "...", "side": "long_a"|"short_a"|"both",
 "mode": "level"|"z", "entry": number, "exit": number, "max_hold_days": integer,
 "claimed_annual_return_pct": number|null}
Meaning: the spread is ln(price of buy_leg / price of other_leg) after both are normalised to
Rs per 10 g of 999 gold. side long_a = buy buy_leg when it is cheap by `entry`; short_a = sell
buy_leg when it is rich by `entry`; both = either direction. mode level = entry/exit in basis
points of that gap (1% = 100); mode z = in standard deviations. exit = the remaining gap at which
the trade closes (0 = back to parity or mean). Convert monthly claims to annual (x12).
If the tip is not about the price gap between two of these gold contracts, set in_scope false."""


def parse_ai(text: str) -> Rule | None:
    from . import ai

    if not ai.has_key():
        return None
    data, by = ai.ask_json(AI_SYSTEM, f"Tip:\n{text}")
    if not isinstance(data, dict):
        return None
    if data.get("in_scope") is False:
        return Rule("GOLDM", "GOLDTEN", source=f"AI · {by}", notes=["out of scope"])
    try:
        a, b = str(data["buy_leg"]).upper(), str(data["other_leg"]).upper()
        side, mode = data.get("side", "long_a"), data.get("mode", "level")
        entry, exit_ = float(data["entry"]), float(data.get("exit") or 0)
        hold = int(data.get("max_hold_days") or 20)
        claimed = data.get("claimed_annual_return_pct")
        claimed = float(claimed) if claimed not in (None, "") else None
    except (KeyError, TypeError, ValueError):
        return None
    if a not in SYMBOLS or b not in SYMBOLS or a == b or side not in ("long_a", "short_a", "both") \
            or mode not in ("level", "z") or not entry > 0 or abs(exit_) >= entry:
        return None
    if mode == "level" and entry < 5:  # the model returned percent, not bps
        entry, exit_ = entry * 100, exit_ * 100
    rule = Rule(a, b, side, mode, entry, exit_, max(1, min(hold, 120)), claimed, f"AI · {by}")
    rule.red_flags = red_flags(text, rule)
    return rule


def _confident(rule: Rule, text: str) -> bool:
    """The pattern reader is trusted when it found everything without guessing."""
    if rule.notes:
        return False
    explicit_both = re.search(r"both ways|either (way|side)|whichever|sigma|σ|z.?score|standard dev|\bmean\b", text, flags=re.I)
    if rule.side == "both" and not explicit_both:
        return False
    mentions_return = re.search(r"%\s*(?:returns?|profit|gains?)?\s*(?:a|per|every|har|/)?\s*\w*\s*"
                                r"(year|month|week|annum|mahin|saal|haft)", text, flags=re.I)
    return not (mentions_return and rule.claimed_annual_pct is None)


def parse_tip(text: str) -> Rule | None:
    """Instant pattern reader first; the AI only when the wording is too messy for it.

    Free AI models can take a minute, so clear tips never wait on them.
    """
    pattern = parse_rules(text)
    if pattern is not None and _confident(pattern, text):
        return pattern
    rule = parse_ai(text)
    if rule is not None and "out of scope" not in rule.notes:
        if rule.claimed_annual_pct is None and pattern is not None:
            rule.claimed_annual_pct = pattern.claimed_annual_pct
        return rule
    if rule is not None and pattern is None:
        return rule
    return pattern


def red_flags(text: str, rule: Rule) -> list[str]:
    flags = []
    if re.search(r"guarantee|assured|sure.?shot|risk.?free|no loss|100%|pakk[ai]|fix(ed)? return", text, flags=re.I):
        flags.append("Promises guaranteed or risk-free returns. No market trade is risk-free.")
    if rule.claimed_annual_pct is not None and rule.claimed_annual_pct > 30:
        flags.append(f"Claims {rule.claimed_annual_pct:.0f}% a year, far above what spread trades usually earn.")
    if re.search(r"join|telegram|whatsapp|vip|premium group|dm me|subscribe", text, flags=re.I):
        flags.append("Pushes you to a paid group or DM: a common finfluencer pattern SEBI warns about.")
    return flags


# ---------------------------------------------------------------- evaluation
def _annual_return_pct(res, pf, cfg: BacktestConfig, a: str, b: str) -> float:
    sa, sb = SPECS[a], SPECS[b]
    lots_a, lots_b = ((LEG_GRAMS / sa.lot_grams, LEG_GRAMS / sb.lot_grams) if cfg.gram_matched else (1.0, 1.0))
    capital = np.maximum(pf["close_a"] * lots_a * sa.rupees_per_point, pf["close_b"] * lots_b * sb.rupees_per_point).mean()
    years = max((pf.index[-1] - pf.index[0]).days / 365.25, 1e-9)
    return float(res.daily["net"].sum() / capital / years * 100) if capital else 0.0


def evaluate(rule: Rule, ws, base: BacktestConfig | None = None) -> dict:
    pf = pair_frame(ws.df, ws.curves, rule.buy_leg, rule.other_leg, ws.roll_bdays)
    cfg0 = replace(base or BacktestConfig(), threshold_mode=rule.mode, sides=rule.side,
                   entry_z=rule.entry, exit_z=rule.exit, max_hold=rule.max_hold)
    gold = ws.front.xs("GOLDM", level="symbol")["px10"]
    steps = []
    for name, cfg in ladder_configs(cfg0):
        res = run_pair(pf, cfg, ws.prices)
        steps.append({"name": name, "net": res.metrics["net_pnl"], "trades": res.metrics["trades"],
                      "ann_pct": _annual_return_pct(res, pf, cfg, rule.buy_leg, rule.other_leg),
                      "result": res})
    naive, honest = steps[0], steps[-1]
    drops = []
    for prev, cur in zip(steps, steps[1:]):
        d = prev["net"] - cur["net"]
        if d > 0:
            drops.append((REASONS.get(cur["name"], cur["name"]), d))
    total = sum(d for _, d in drops) or 1.0
    breakdown = [(r, d, d / total * 100) for r, d in sorted(drops, key=lambda x: -x[1])]
    hm = honest["result"].metrics
    verdict = _verdict(rule, honest["ann_pct"], hm["trades"], hm["sharpe"])
    return {
        "rule": rule, "steps": steps, "naive": naive, "honest": honest, "breakdown": breakdown,
        "verdict": verdict, "pair_frame": pf,
        "attr_naive": attribution(naive["result"].daily["net"], gold),
        "attr_honest": attribution(honest["result"].daily["net"], gold),
        "days": len(pf), "first": pf.index[0], "last": pf.index[-1],
    }


def _verdict(rule: Rule, honest_ann: float, trades: int, sharpe: float) -> tuple[str, str, str]:
    claim = rule.claimed_annual_pct
    if trades == 0:
        return ("never", "🤷 This rule never fires on honest data",
                "After real contracts, carry and liquidity checks, the condition was never met. "
                "A tip that never triggers can't deliver its promise.")
    if honest_ann <= 0:
        return ("fail", "❌ Doesn't survive real trading",
                f"Tested honestly it lost money: {honest_ann:+.1f}% a year over {trades} trades.")
    if claim and honest_ann < 0.5 * claim:
        return ("hype", "⚠️ Far smaller than claimed",
                f"Honest result {honest_ann:+.1f}% a year against the claimed {claim:.0f}%, over {trades} trades.")
    if trades < 20:
        return ("thin", "⚠️ Too few trades to trust",
                f"{honest_ann:+.1f}% a year, but from only {trades} trades. That could easily be luck.")
    return ("pass", "✅ Holds up on real data (so far)",
            f"{honest_ann:+.1f}% a year over {trades} trades (Sharpe {sharpe:.2f}). Past results don't guarantee the future.")


EXAMPLES = [
    "Buy GOLDPETAL when it's 1% cheaper than GOLDM, sell when it comes back to normal. Easy 40% a year, guaranteed! 🚀 Join my VIP Telegram",
    "GOLDGUINEA premium over GOLDTEN above 0.8%? Sell guinea, buy GOLDTEN. Exit when the premium halves. 5% monthly returns.",
    "When the GOLDTEN vs GOLDGUINEA spread goes beyond 2 sigma, trade it back to the mean. Hold max 15 days.",
]
