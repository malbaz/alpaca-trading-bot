"""
منطق الإشارة والحسابات — دوال نقية بلا اتصال بالشبكة (سهلة الاختبار).
"""
from dataclasses import dataclass
from typing import Optional, Sequence

from config import Settings


@dataclass
class Signal:
    symbol: str
    price: float
    momentum_pct: float
    volume_10m: int
    bid: float
    ask: float


def spread_pct(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0 or ask < bid:
        return float("inf")
    mid = (bid + ask) / 2
    return (ask - bid) / mid * 100


def evaluate(symbol: str, closes: Sequence[float], volumes: Sequence[int],
             bid: float, ask: float, s: Settings) -> Optional[Signal]:
    """
    closes/volumes: شموع الدقيقة مرتبة من الأقدم للأحدث.
    يعيد Signal إذا تحققت كل الشروط، وإلا None.
    """
    w = s.momentum_window_min
    if len(closes) < w + 1:
        return None
    price = float(closes[-1])
    if not (s.min_price <= price <= s.max_price):
        return None
    ref = float(closes[-1 - w])  # السعر قبل w دقيقة بالضبط
    if ref <= 0:
        return None
    momentum = (price - ref) / ref * 100
    vol10 = int(sum(volumes[-10:]))
    if momentum < s.min_momentum_pct or vol10 < s.min_volume_10m:
        return None
    # منع مطاردة شمعة واحدة ضخمة: آخر شمعة لا يجب أن تكون كل الحركة
    if len(closes) >= 2 and closes[-2] > 0:
        last_jump = (price - closes[-2]) / closes[-2] * 100
        if last_jump > momentum * 0.8 and momentum > 0:
            return None
    if spread_pct(bid, ask) > s.max_spread_pct:
        return None
    return Signal(symbol, price, round(momentum, 2), vol10, bid, ask)


def exit_levels(entry: float, s: Settings):
    target = round(entry * (1 + s.take_profit_pct / 100), 2)
    stop = round(entry * (1 - s.stop_loss_pct / 100), 2)
    return target, stop


def position_qty(price: float, buying_power: float, s: Settings) -> int:
    """
    الكمية = الأصغر بين: الميزانية/السعر ، المخاطرة بالدولار/مسافة الوقف.
    يعيد 0 إذا كانت الصفقة لا تحقق الحد الأدنى (لا نشتري سهماً واحداً بالإجبار).
    """
    if price <= 0:
        return 0
    budget = min(s.trade_budget_usd, buying_power)
    if budget < s.min_budget_usd:
        return 0
    by_budget = int(budget // price)
    stop_distance = price * s.stop_loss_pct / 100
    by_risk = int(s.risk_per_trade_usd // stop_distance) if stop_distance > 0 else by_budget
    return max(0, min(by_budget, by_risk))


def should_exit(entry: float, current: float, s: Settings) -> Optional[str]:
    """للتداول الممتد حيث لا تدعم Alpaca أوامر Bracket."""
    if entry <= 0 or current <= 0:
        return None
    change = (current - entry) / entry * 100
    if change >= s.take_profit_pct:
        return f"جني أرباح (+{change:.2f}%)"
    if change <= -s.stop_loss_pct:
        return f"وقف خسارة ({change:.2f}%)"
    return None
