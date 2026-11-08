import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Settings  # noqa: E402
import strategy  # noqa: E402

S = replace(Settings(), min_price=1.5, max_price=16, momentum_window_min=5, min_momentum_pct=3.0,
            min_volume_10m=20000, max_spread_pct=0.6, trade_budget_usd=50, min_budget_usd=10,
            risk_per_trade_usd=2.0, take_profit_pct=4.5, stop_loss_pct=2.5)


def test_old_fake_spread_would_always_fail():
    # الكود القديم: bid=price*0.995, ask=price*1.005 → ~1% أعلى من الحد
    assert strategy.spread_pct(9.95, 10.05) > 0.5


def test_real_tight_spread_passes():
    assert strategy.spread_pct(10.00, 10.02) < 0.6


def test_signal_on_steady_momentum():
    closes = [5.00, 5.00, 5.00, 5.04, 5.08, 5.12, 5.16, 5.20]
    vols = [3000] * 8
    sig = strategy.evaluate("ABC", closes, vols, 5.19, 5.21, S)
    assert sig is not None and sig.momentum_pct >= 3.0


def test_no_signal_on_weak_momentum():
    closes = [5.00] * 7 + [5.05]
    assert strategy.evaluate("ABC", closes, [5000] * 8, 5.04, 5.06, S) is None


def test_no_signal_on_wide_spread():
    closes = [5.00, 5.00, 5.00, 5.04, 5.08, 5.12, 5.16, 5.20]
    assert strategy.evaluate("ABC", closes, [3000] * 8, 5.10, 5.25, S) is None


def test_no_signal_outside_price_range():
    closes = [1.0, 1.0, 1.0, 1.02, 1.04, 1.06, 1.08, 1.10]
    assert strategy.evaluate("ABC", closes, [9000] * 8, 1.09, 1.10, S) is None


def test_exit_levels():
    assert strategy.exit_levels(10.0, S) == (10.45, 9.75)


def test_qty_limited_by_budget():
    # $50 / $10 = 5 ، المخاطرة 2$ / (10*2.5%) = 8 → 5
    assert strategy.position_qty(10.0, 1000, S) == 5


def test_qty_limited_by_risk():
    # سعر 4$: 12 من الميزانية مقابل 20 من المخاطرة → 12
    assert strategy.position_qty(4.0, 1000, S) == 12


def test_qty_zero_when_budget_too_low():
    assert strategy.position_qty(5.0, 8.0, S) == 0


def test_should_exit():
    assert "جني" in strategy.should_exit(10.0, 10.46, S)
    assert "وقف" in strategy.should_exit(10.0, 9.74, S)
    assert strategy.should_exit(10.0, 10.1, S) is None
