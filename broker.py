"""
نقطة الاتصال الوحيدة مع Alpaca.
- TradingClient: الحساب والأوامر والساعة.
- StockHistoricalDataClient: الأسعار والعروض (وليس TradingClient).
كل الملفات تستخدم هذه الكائنات، فلا يمكن أن يختلط الحساب التجريبي بالحقيقي.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from config import settings

try:
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MarketMoversRequest, MostActivesRequest
except ImportError:  # نسخة قديمة من alpaca-py
    ScreenerClient = None

log = logging.getLogger("broker")

trading = TradingClient(settings.api_key, settings.secret_key, paper=settings.paper)
data = StockHistoricalDataClient(settings.api_key, settings.secret_key)
FEED = DataFeed.SIP if settings.data_feed == "sip" else DataFeed.IEX


screener = ScreenerClient(settings.api_key, settings.secret_key) if ScreenerClient else None


def top_movers(top: int = 50):
    """الأكثر صعودًا [(symbol, %change, price)] والأكثر نشاطًا [symbol]. فشل = قوائم فارغة."""
    gainers, actives = [], []
    if not screener:
        return gainers, actives
    top = max(1, min(50, int(top)))
    try:
        m = screener.get_market_movers(MarketMoversRequest(top=top))
        gainers = [(g.symbol, float(g.percent_change), float(g.price)) for g in m.gainers]
    except Exception as e:
        log.warning("movers error: %s", e)
    try:
        a = screener.get_most_actives(MostActivesRequest(top=top))
        actives = [x.symbol for x in a.most_actives]
    except Exception as e:
        log.warning("most actives error: %s", e)
    return gainers, actives


def _chunks(items: List[str], n: int = 100):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def snapshots(symbols: List[str]) -> Dict:
    """أحدث صفقة + أفضل عرض/طلب حقيقي لكل الأسهم في طلبات قليلة."""
    out = {}
    for chunk in _chunks(symbols):
        try:
            out.update(data.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=chunk, feed=FEED)))
        except Exception as e:
            log.warning("snapshot error: %s", e)
    return out


def minute_bars(symbols: List[str], minutes: int = 15) -> Dict[str, list]:
    """شموع الدقيقة لآخر N دقيقة لكل الأسهم (يشمل التداول الممتد)."""
    start = datetime.now(timezone.utc) - timedelta(minutes=minutes + 2)
    out: Dict[str, list] = {}
    for chunk in _chunks(symbols):
        try:
            res = data.get_stock_bars(StockBarsRequest(
                symbol_or_symbols=chunk, timeframe=TimeFrame.Minute, start=start, feed=FEED))
            out.update(res.data)
        except Exception as e:
            log.warning("bars error: %s", e)
    return out


def market_phase() -> str:
    """REGULAR أو EXTENDED أو CLOSED حسب ساعة Alpaca الرسمية."""
    clock = trading.get_clock()
    if clock.is_open:
        return "REGULAR"
    # التداول الممتد في Alpaca: 4:00–9:30 و 16:00–20:00 بتوقيت نيويورك أيام العمل
    from zoneinfo import ZoneInfo
    now_et = clock.timestamp.astimezone(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return "CLOSED"
    minutes = now_et.hour * 60 + now_et.minute
    # يوم عمل لكن السوق مغلق: هل اليوم عطلة؟ إذا كان الافتتاح القادم بعد أكثر من يوم فهي عطلة
    hours_to_open = (clock.next_open - clock.timestamp).total_seconds() / 3600
    pre = 4 * 60 <= minutes < 9 * 60 + 30 and hours_to_open < 6
    post = 16 * 60 <= minutes < 20 * 60 and hours_to_open < 18
    return "EXTENDED" if (pre or post) else "CLOSED"
