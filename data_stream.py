import os
import sys
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed
from order_manager import order_manager
from risk_engine import risk_engine

# مفاتيح الحساب
API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()

# استخدام تغذية SIP الشاملة عبر DataFeed.SIP
try:
    stream = StockDataStream(API_KEY, SECRET_KEY, feed=DataFeed.SIP)
except Exception:
    # احتياطي في حال كانت نسخة المكتبة أقدم
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

price_history = {}

async def handle_trade(trade):
    symbol = trade.symbol
    price = float(trade.price)
    size = int(trade.size)
    
    if symbol not in price_history:
        price_history[symbol] = {"prices": [], "volume": 0}
        
    price_history[symbol]["prices"].append(price)
    price_history[symbol]["volume"] += size
    
    if len(price_history[symbol]["prices"]) > 100:
        price_history[symbol]["prices"].pop(0)

    if 1.00 <= price <= 16.00:
        first_price = price_history[symbol]["prices"][0]
        momentum_pct = ((price - first_price) / first_price) * 100
        
        if momentum_pct >= 2.5 and price_history[symbol]["volume"] >= 30000:
            bid = price * 0.995
            ask = price * 1.005
            
            if risk_engine.is_trade_allowed(symbol, bid, ask):
                result = order_manager.process_buy_signal(symbol, price, budget=50.0)
                print(f"⚡ [SIP Live Signal] {symbol} | السعر: ${price} | النتيجة: {result}", flush=True)

def start_stream():
    try:
        order_manager.reconcile_positions()
    except Exception as e:
        print(f"⚠️ تنبيه أثناء مطابقة التدويرات: {e}", flush=True)
        
    print("🚀 بدء الاستماع اللحظي المستمر عبر Alpaca SIP Data...", flush=True)
    for symbol in WATCHLIST:
        stream.subscribe_trades(handle_trade, symbol)
    stream.run()

if __name__ == "__main__":
    start_stream()
