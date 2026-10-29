import os, sys
from dataclasses import replace
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Settings
import strategy

S = replace(Settings(), min_price=1.5, max_price=16, momentum_window_min=5, min_momentum_pct=3.0,
            min_volume_10m=20000, max_spread_pct=0.6, volume_surge_mult=2.0, near_high_pct=1.0,
            near_hod_pct=1.5, min_day_change_pct=5.0, movers_max_symbols=40)
CL = [5.0]*10 + [5.02, 5.05, 5.08, 5.12, 5.40]
VO = [2500]*14 + [9000]

def test_buys_at_high_of_day():
    assert strategy.evaluate("X", CL, VO, 5.39, 5.41, S, day_high=5.42) is not None

def test_rejects_far_below_high_of_day():
    assert strategy.evaluate("X", CL, VO, 5.39, 5.41, S, day_high=6.00) is None

def test_partial_sells_half():
    assert strategy.partial_qty(10, S) == 5
    assert strategy.partial_qty(9, S) == 4
    assert strategy.partial_qty(2, S) == 1

def test_partial_skipped_for_one_share():
    assert strategy.partial_qty(1, S) == 0

def test_defaults_partial_at_3_5_pct():
    d = Settings()
    assert (d.partial_tp_pct, d.partial_sell_pct) == (3.5, 50.0)

def test_trailing_after_partial_has_no_activation_wait():
    lvl = strategy.trailing_stop_level(2.0, 2.07, S, active=True)
    assert lvl is not None and lvl >= 2.0
    assert strategy.trailing_stop_level(2.0, 2.07, S) is None

def test_trailing_follows_peak_without_cap():
    lvl = strategy.trailing_stop_level(2.0, 4.0, S, active=True)
    assert abs(lvl - 4.0 * (1 - S.trail_back_pct / 100)) < 1e-9

def test_universe_adds_gainers_and_filters():
    g = [("NEWS", 25.0, 4.0), ("SLOW", 2.0, 4.0), ("PRICY", 30.0, 90.0), ("BBAI", 9.0, 2.4)]
    u = strategy.merge_universe(["BBAI"], g, ["NEWS", "AAPL"], S)
    assert u == ["BBAI", "NEWS"]
