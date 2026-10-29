"""Pure signal calculations; shared exit levels for sizing and local exits."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from math import isfinite
from typing import Optional, Sequence

from config import Settings

MIN_STOP_PCT = 3.0
MIN_REWARD_RISK = 2.0
# هامش فوق سعر الدخول عند رفع الوقف للتعادل (يغطي الرسوم والانزلاق)
BREAKEVEN_BUFFER = 1.002


@dataclass
class Signal:
    symbol: str
    price: float
    momentum_pct: float
    volume_10m: int
    bid: float
    ask: float


def spread_pct(bid: float, ask: float) -> float:
    if not isfinite(bid) or not isfinite(ask) or bid <= 0 or ask <= 0 or ask < bid:
        return float("inf")
    return (ask - bid) / ((bid + ask) / 2) * 100


def evaluate(symbol: str, closes: Sequence[float], volumes: Sequence[int],
             bid: float, ask: float, s: Settings) -> Optional[Signal]:
    """One-minute bars, oldest first. No ATR/daily-change data supplied here."""
    w = s.momentum_window_min
    if w < 1 or len(closes) < max(w + 1, 10) or len(volumes) != len(closes):
        return None
    if any(not isfinite(float(x)) or float(x) <= 0 for x in closes):
        return None
    if any(not isfinite(float(v)) or v < 0 for v in volumes):
        return None
    price = float(closes[-1])
    if not (s.min_price <= price <= s.max_price):
        return None
    ref = float(closes[-1 - w])
    momentum = (price - ref) / ref * 100
    vol10 = int(sum(volumes[-10:]))
    if momentum < s.min_momentum_pct or vol10 < s.min_volume_10m:
        return None
    # اختراق عند القمة: لا نشتري سهمًا تراجع من موجته
    recent_high = max(float(x) for x in closes[-15:])
    if price < recent_high * (1 - s.near_high_pct / 100):
        return None
    # طفرة سيولة: حجم آخر شمعة أعلى بوضوح من متوسط ما قبلها
    prev = [int(v) for v in volumes[-11:-1]]
    avg_prev = sum(prev) / len(prev) if prev else 0
    if avg_prev > 0 and volumes[-1] < avg_prev * s.volume_surge_mult:
        return None
    if spread_pct(bid, ask) > s.max_spread_pct:
        return None
    return Signal(symbol, price, round(momentum, 2), vol10, bid, ask)


def exit_levels(entry: float, s: Settings):
    """Return (target, stop). Round outward to preserve >=3% stop and >=2R.

    Existing callers remain compatible. These are planned price levels, not
    a guarantee on realized losses: gaps, slippage and fees can exceed them.
    """
    values = (entry, s.stop_loss_pct, s.take_profit_pct)
    if any(not isfinite(float(v)) for v in values) or entry <= 0:
        raise ValueError("Entry and exit settings must be finite; entry must be positive")
    if s.stop_loss_pct <= 0 or s.stop_loss_pct >= 100 or s.take_profit_pct < 0:
        raise ValueError("Invalid exit percentages")
    e = Decimal(str(entry))
    stop_pct = Decimal(str(max(MIN_STOP_PCT, s.stop_loss_pct)))
    tick = Decimal("0.01") if e >= 1 else Decimal("0.0001")
    stop = (e * (1 - stop_pct / 100)).quantize(tick, rounding=ROUND_FLOOR)
    if stop <= 0 or stop >= e:
        raise ValueError("No valid positive stop at this price precision")
    distance = e - stop
    target = max(e * (1 + Decimal(str(s.take_profit_pct)) / 100),
                 e + Decimal(str(MIN_REWARD_RISK)) * distance)
    target = target.quantize(tick, rounding=ROUND_CEILING)
    return float(target), float(stop)


def position_qty(price: float, buying_power: float, s: Settings) -> int:
    """Whole shares limited by budget AND actual rounded stop distance."""
    values = (price, buying_power, s.trade_budget_usd, s.min_budget_usd,
              s.risk_per_trade_usd)
    if any(not isfinite(float(v)) for v in values):
        return 0
    if price <= 0 or buying_power <= 0 or s.trade_budget_usd <= 0 or s.risk_per_trade_usd <= 0:
        return 0
    budget = min(s.trade_budget_usd, buying_power)
    if budget < s.min_budget_usd:
        return 0
    try:
        _, stop = exit_levels(price, s)
    except ValueError:
        return 0
    e = Decimal(str(price))
    distance = e - Decimal(str(stop))
    by_budget = int(Decimal(str(budget)) // e)
    by_risk = int(Decimal(str(s.risk_per_trade_usd)) // distance)
    return max(0, min(by_budget, by_risk))


def trailing_stop_level(entry: float, peak: float, s: Settings) -> Optional[float]:
    """مستوى الوقف المتحرك: None قبل التفعيل، وبعده لا ينزل أبدًا عن التعادل.

    التفعيل عندما يبلغ أعلى سعر (peak) ربح TRAIL_ACTIVATE_PCT.
    بعدها الوقف = الأعلى بين (التعادل + هامش) و (peak - TRAIL_BACK_PCT).
    """
    if not isfinite(entry) or not isfinite(peak) or entry <= 0 or peak <= 0:
        return None
    if peak < entry * (1 + s.trail_activate_pct / 100):
        return None
    return max(entry * BREAKEVEN_BUFFER, peak * (1 - s.trail_back_pct / 100))


def should_exit(entry: float, current: float, s: Settings) -> Optional[str]:
    """الفحص المحلي للوقف الثابت والهدف (يُستخدم قبل تفعيل الوقف المتحرك).

    بعد تفعيل الوقف المتحرك يستخدم المحرك trailing_stop_level بدلًا من هذا.
    """
    if not isfinite(entry) or not isfinite(current) or entry <= 0 or current <= 0:
        return None
    target, stop = exit_levels(entry, s)
    change = (current - entry) / entry * 100
    if current >= target:
        return f"جني أرباح (+{change:.2f}%)"
    if current <= stop:
        return f"وقف خسارة ({change:.2f}%)"
    return None
