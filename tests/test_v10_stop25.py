"""قواعد وقف الخسارة 25% — تُشغَّل: python3 test_v10_stop25.py

اختبارات محلية فقط: لا اتصال بـAlpaca ولا أوامر حقيقية.
"""
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# متغيرات بيئة وهمية حتى لا يفشل استيراد config
os.environ.setdefault("ALPACA_API_KEY", "test")
os.environ.setdefault("ALPACA_SECRET_KEY", "test")

from config import Settings  # noqa: E402
import strategy  # noqa: E402


def test_default_stop_is_25_percent():
    s = Settings()
    assert s.stop_loss_pct == 25.0, s.stop_loss_pct
    assert strategy.MIN_STOP_PCT == 25.0, strategy.MIN_STOP_PCT


def test_stop_is_25_percent_below_entry():
    s = Settings()
    _, stop = strategy.exit_levels(2.50, s)
    assert stop == 1.87, stop                      # 2.50 - 25% (تقريب للأسفل)
    assert round((2.50 - stop) / 2.50 * 100, 2) == 25.2  # التقريب يوسّع الوقف قليلًا


def test_stop_is_25_percent_below_entry_exact():
    s = Settings()
    _, stop = strategy.exit_levels(4.00, s)
    assert stop == 3.00, stop                      # 4.00 - 25% بالضبط


def test_env_stop_below_minimum_stays_25():
    """متغير Railway يطلب وقف 3% — الحد الأدنى 25% يبقى أعلى."""
    s = replace(Settings(), stop_loss_pct=3.0)
    _, stop = strategy.exit_levels(2.50, s)
    assert stop == 1.87, stop


def test_position_qty_shrinks_with_wider_stop():
    """وقف أوسع = مسافة أكبر = عدد أسهم أقل لنفس حد المخاطرة بالدولار."""
    s = Settings()
    qty = strategy.position_qty(2.50, 100.0, s)
    # مسافة الوقف 0.63$ وحد المخاطرة 1$ → سهم واحد كحد أقصى
    assert qty == 1, qty


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
