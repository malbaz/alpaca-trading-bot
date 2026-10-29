import os, sys
from dataclasses import replace
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Settings
import strategy

S = replace(Settings(), min_price=1.5, max_price=16, momentum_window_min=5, min_momentum_pct=3.0,
            min_volume_10m=20000, max_spread_pct=0.6, volume_surge_mult=2.0, near_high_pct=1.0)

def test_buys_fast_breakout_with_volume_surge():
    closes = [5.0]*10 + [5.02, 5.05, 5.08, 5.12, 5.40]   # قفزة قوية في آخر شمعة
    vols = [2500]*14 + [9000]
    assert strategy.evaluate("X", closes, vols, 5.39, 5.41, S) is not None

def test_rejects_after_pullback_from_high():
    closes = [5.0]*9 + [5.1, 5.3, 5.6, 5.5, 5.35, 5.30]
    vols = [2500]*14 + [9000]
    assert strategy.evaluate("X", closes, vols, 5.29, 5.31, S) is None

def test_rejects_without_volume_surge():
    closes = [5.0]*10 + [5.02, 5.05, 5.08, 5.12, 5.40]
    vols = [3000]*15
    assert strategy.evaluate("X", closes, vols, 5.39, 5.41, S) is None

def test_defaults_wider_trailing_and_target():
    d = Settings()
    assert (d.trail_activate_pct, d.trail_back_pct, d.take_profit_pct) == (4.5, 3.0, 15.0)

def test_entry_window():
    from zoneinfo import ZoneInfo
    import engine
    ny = ZoneInfo("America/New_York")
    f = engine.Engine.entry_window_open
    assert not f(datetime(2026,10,29,9,40,tzinfo=ny))
    assert f(datetime(2026,10,29,9,45,tzinfo=ny))
    assert f(datetime(2026,10,29,15,29,tzinfo=ny))
    assert not f(datetime(2026,10,29,15,30,tzinfo=ny))
