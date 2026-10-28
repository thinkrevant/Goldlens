import pandas as pd
import pytest

from goldlens import tipcheck
from goldlens.backtest import BacktestConfig, _targets


def test_pattern_reader_handles_the_examples():
    r1 = tipcheck.parse_rules(tipcheck.EXAMPLES[0])
    assert (r1.buy_leg, r1.other_leg, r1.side, r1.mode) == ("GOLDPETAL", "GOLDM", "long_a", "level")
    assert r1.entry == 100 and r1.exit == 0 and r1.claimed_annual_pct == 40
    assert len(r1.red_flags) == 3  # guaranteed, >30%/yr, VIP Telegram

    r2 = tipcheck.parse_rules(tipcheck.EXAMPLES[1])
    assert (r2.buy_leg, r2.other_leg, r2.side) == ("GOLDTEN", "GOLDGUINEA", "long_a")
    assert r2.entry == 80 and r2.exit == 40 and r2.claimed_annual_pct == 60  # 5% monthly -> 60% a year

    r3 = tipcheck.parse_rules(tipcheck.EXAMPLES[2])
    assert (r3.side, r3.mode, r3.entry, r3.max_hold) == ("both", "z", 2.0, 15)


def test_out_of_scope_tip_is_not_guessed():
    assert tipcheck.parse_rules("Buy Reliance at 2800, target 3100, stop loss 2700") is None


def test_one_sided_rules_only_trade_their_side():
    z = pd.Series([0, -150, -50, 20, 0, 150, 60, -10])
    cfg = BacktestConfig(threshold_mode="level", entry_z=100, exit_z=0, max_hold=99)
    assert list(_targets(z, cfg)) == [0, 1, 1, 0, 0, -1, -1, 0]
    assert list(_targets(z, BacktestConfig(threshold_mode="level", entry_z=100, exit_z=0, max_hold=99,
                                           sides="long_a"))) == [0, 1, 1, 0, 0, 0, 0, 0]
    assert list(_targets(z, BacktestConfig(threshold_mode="level", entry_z=100, exit_z=0, max_hold=99,
                                           sides="short_a"))) == [0, 0, 0, 0, 0, -1, -1, 0]


@pytest.mark.parametrize("ann,trades,claim,kind", [
    (0.0, 0, None, "never"), (-1.7, 56, 40, "fail"), (3.0, 18, None, "thin"),
    (0.4, 30, 60, "hype"), (8.0, 40, 10, "pass"),
])
def test_verdicts(ann, trades, claim, kind):
    rule = tipcheck.Rule("GOLDTEN", "GOLDGUINEA", claimed_annual_pct=claim)
    assert tipcheck._verdict(rule, ann, trades, 1.0)[0] == kind


@pytest.fixture(scope="module")
def ws():
    from goldlens.config import PANEL_PATH
    if not PANEL_PATH.exists():
        pytest.skip("no cached MCX panel")
    from goldlens.pipeline import build_workspace
    return build_workspace()


def test_evaluate_runs_the_full_ladder(ws):
    ev = tipcheck.evaluate(tipcheck.parse_rules(tipcheck.EXAMPLES[0]), ws)
    assert len(ev["steps"]) == 7 and ev["verdict"][0] in {"fail", "hype", "thin", "pass", "never"}
    shares = [p for _, _, p in ev["breakdown"]]
    assert not shares or abs(sum(shares) - 100) < 1e-6
    # the honest step must include trading costs
    assert ev["honest"]["result"].metrics["costs"] > 0 or ev["honest"]["trades"] == 0


def test_clear_tips_skip_the_slow_ai(monkeypatch):
    called = []
    monkeypatch.setattr(tipcheck, "parse_ai", lambda text: called.append(text))
    for t in tipcheck.EXAMPLES:
        assert tipcheck.parse_tip(t) is not None
    assert called == []  # every example is clear enough for the instant reader
    tipcheck.parse_tip("petal is cheap these days, maybe buy?")
    assert len(called) == 1  # vague wording goes to the AI
