import os
import asyncio
from alpaca.data.live import StockDataStream
from order_manager import order_manager
from risk_engine import risk_engine

# مفاتيح الحساب والاشتراك المدفوع (SIP Feed)
API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()

# استخدام تغذية sip للبيانات الكاملة
stream = StockDataStream(API_KEY, SECRET_KEY, feed='sip')

WATCHLIST = [
    "BOOM", "BRBR", "BNED", "BOF", "BLZE", "BKKT", "BIAF", "AXIL", 
    "AYTU", "AVO", "AVPT", "AMOD", "NSTR", "AIXI", "CYCU", "PMI", 
    "AMPL", "AMPX", "ABSI", "AMBO", "AEYE", "AIOT", "AENT", "ADTN", 
    "ABEO", "ABTE", "ZNB", "EEIQ", "HSCS", "CVM", "EFOI", "CSAI", 
    "LONA", "AZ", "JDZG", "RTB", "LNZA", "MTNB", "IDAI", "AIRG", 
    "BMHL", "PICS", "RGC", "HYLN", "FISN", "CJMB", "BTLN", "INTS", 
    "DFNS", "OSG", "EP", "CTNT", "DDD", "RXT", "SOC", "CUVL", 
    "SOTK", "KOPN", "SHIM", "OPTX", "INDP", "ATRA", "MYGN", "NFE", 
    "ABLV", "GRDX", "WVVI", "SDEV", "GOW", "NNBR", "NAUT", "ICU", 
    "REBN", "NEOV", "FEAM", "SSM", "IMC", "CELU", "ONCY", "ABVC", 
    "TLSI", "DBRG", "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", 
    "LUNR", "SERV", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "KULR", "RIG", "GTEC", "PDSB", "GRML", "BFLY", "EAF", "IPDN", "WFCF"
]

# ذاكرة لحظية لتتبع الأحجام والأسعار
price_history = {}

async def handle_trade(trade):
    symbol = trade.symbol
    price = float(trade.price)
    size = int(trade.size)
    
    if symbol not in price_history:
        price_history[symbol] = {"prices": [], "volume": 0}
        
    price_history[symbol]["prices"].append(price)
    price_history[symbol]["volume"] += size
    
    # الاحتفاظ بآخر 100 صفقة فقط في الذاكرة
    if len(price_history[symbol]["prices"]) > 100:
        price_history[symbol]["prices"].pop(0)

    # فحص الفلاتر السعرية والزخم فورياً (Sub-second)
    if 1.00 <= price <= 16.00:
        first_price = price_history[symbol]["prices"][0]
        momentum_pct = ((price - first_price) / first_price) * 100
        
        # شرط الزخم الفوري والسريع
        if momentum_pct >= 2.5 and price_history[symbol]["volume"] >= 30000:
            bid = price * 0.998
            ask = price * 1.002
            
            if risk_engine.is_trade_allowed(symbol, bid, ask):
                result = order_manager.process_buy_signal(symbol, price, budget=50.0)
                print(f"⚡ [تنفيذ لحظي SIP] {symbol} | السعر: ${price} | النتيجة: {result}")

def start_stream():
    order_manager.reconcile_positions()
    print("🚀 بدء الاستماع اللحظي عالي السرعة (SIP Feed)...")
    for symbol in WATCHLIST:
        stream.subscribe_trades(handle_trade, symbol)
    stream.run()

if __name__ == "__main__":
    start_stream()
