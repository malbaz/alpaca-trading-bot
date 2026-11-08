"""قواعد وقف الخسارة 10% — تُشغَّل: python3 test_v6_stop.py"""
import os
import sys

for name in ("STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "TRAIL_ACTIVATE_PCT",
             "TRAIL_BACK_PCT", "PARTIAL_TP_PCT", "PARTIAL_SELL_PCT"):
    os.environ.pop(name, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dataclasses import replace  # noqa: E402
import strategy  # noqa: E402
from config import Settings, validate_settings  # noqa: E402


def test_default_stop_is_10_percent():
    s = Settings()
    assert s.stop_loss_pct == 10.0, s.stop_loss_pct
    assert strategy.MIN_STOP_PCT == 10.0, strategy.MIN_STOP_PCT


def test_stop_is_10_percent_below_entry():
    s = Settings()
    target, stop = strategy.exit_levels(2.50, s)
    assert stop == 2.25, stop                      # 2.50 - 10%
    assert round((2.50 - stop) / 2.50 * 100, 2) == 10.0
    assert target >= 2.50 * 1.20, target           # 2R = +20%


def test_floor_blocks_narrower_stop():
    """متغير Railway يطلب وقف 3% — الحد الأدنى 10% يبقى أعلى."""
    s = replace(Settings(), stop_loss_pct=3.0)
    _, stop = strategy.exit_levels(2.50, s)
    assert stop == 2.25, stop


def test_qty_shrinks_with_wider_stop():
    s = Settings()
    assert strategy.position_qty(2.50, 75.0, s) == 4      # 4 x 0.25 = 1$ خطر
    assert strategy.position_qty(3.13, 75.0, s) == 3      # 3 x 0.32 = ~1$ خطر
    assert strategy.position_qty(12.00, 75.0, s) == 0     # خطر السهم > 1$ → لا شراء


def test_settings_still_valid():
    """لا أخطاء في قواعد الخروج (أخطاء المفاتيح غير موجودة في بيئة الاختبار)."""
    errs = [e for e in validate_settings(Settings()) if "غير موجود" not in e]
    assert errs == [], errs


if __name__ == "__main__":
    failed = 0
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL", fn.__name__, "->", exc)
    print("ALL PASS" if not failed else f"{failed} FAILED")
    sys.exit(1 if failed else 0)
