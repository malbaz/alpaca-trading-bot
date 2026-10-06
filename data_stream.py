import os
import asyncio
from alpaca.data.live import StockDataStream

# 1. جلب المفاتيح البيئية
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()

# قائمة الأسهم المراقبة
SYMBOLS = ["BOOM", "BRBR", "BNED", "BOF", "BLZE", "BKKT", "BIAF", "AXIL", "AYTU", "AVO"]

async def handle_trade(trade):
    """
    معالجة كل صفقة منفذة في السوق لحظة بلاحظة
    """
    symbol = trade.symbol
    price = trade.price
    size = trade.size
    timestamp = trade.timestamp
    print(f"⚡ [صفقة حية] {symbol}: السعر=${price:.2f} | الكمية={size} | الوقت={timestamp}")

async def handle_quote(quote):
    """
    معالجة الفارق بين العرض والطلب (Bid/Ask Spread) لحساب التكلفة الحقيقية
    """
    symbol = quote.symbol
    bid = quote.ask_price
    ask = quote.ask_price
    if bid > 0:
        spread_pct = ((ask - bid) / bid) * 100
        print(f"📊 [عرض/طلب] {symbol}: Ask=${ask:.2f} | Bid=${bid:.2f} | السبريد={spread_pct:.2f}%")

def start_live_stream():
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("خطأ: مفاتيح Alpaca غير متوفرة للاتصال الحي.")
        return

    # إنشاء الاتصال الحي مع Alpaca IEX Stream
    stream = StockDataStream(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    # الاشتراك في الصفقات والعروض المباشرة
    stream.subscribe_trades(handle_trade, *SYMBOLS)
    stream.subscribe_quotes(handle_quote, *SYMBOLS)

    print("🚀 تم تشغيل اتصال Alpaca WebSocket المباشر...")
    stream.run()

if __name__ == "__main__":
    start_live_stream()
