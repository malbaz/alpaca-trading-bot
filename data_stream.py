import os
import sys
import json
import asyncio
import websockets
from order_manager import order_manager
from risk_engine import risk_engine

API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()

is_paper = API_KEY.startswith("PK")

# تحديد رابط الـ WebSocket المناسب
if is_paper:
    WS_URL = "wss://stream.data.alpaca.markets/v2/iex"
    print("⚠️ استخدام سيرفر تغذية IEX للبيانات (Paper Keys)...", flush=True)
else:
    WS_URL = "wss://stream.data.alpaca.markets/v2/sip"
    print("✅ استخدام سيرفر تغذية SIP المباشر (Live Keys)...", flush=True)

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

async def process_message(msg):
    try:
        data = json.loads(msg)
        for item in data:
            if item.get("T") == "t":  # صفقة التداول (Trade)
                symbol = item.get("S")
                price = float(item.get("p", 0))
                size = int(item.get("s", 0))

                if not symbol or price == 0:
                    continue

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
                            print(f"⚡ [Live Signal] {symbol} | السعر: ${price} | النتيجة: {result}", flush=True)
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة الرسالة: {e}", flush=True)

async def run_websocket():
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                # 1. انتظار رسالة الترحيب من السيرفر
                res = await ws.recv()
                
                # 2. إرسال بيانات المصادقة
                auth_payload = {
                    "action": "auth",
                    "key": API_KEY,
                    "secret": SECRET_KEY
                }
                await ws.send(json.dumps(auth_payload))
                
                auth_res = await ws.recv()
                print(f"🔐 نتيجة المصادقة: {auth_res}", flush=True)

                # 3. الاشتراك في أسعار قائمة المتابعة
                sub_payload = {
                    "action": "subscribe",
                    "trades": WATCHLIST
                }
                await ws.send(json.dumps(sub_payload))
                print("🚀 تم الاشتراك في بث الأسعار المباشر بنجاح!", flush=True)

                # 4. استلام الرسائل باستمرار
                while True:
                    msg = await ws.recv()
                    await process_message(msg)

        except Exception as e:
            print(f"❌ انقطع الاتصال بالـ WebSocket: {e} - جاري إعادة الاتصال خلال 5 ثوانٍ...", flush=True)
            await asyncio.sleep(5)

def start_stream():
    try:
        order_manager.reconcile_positions()
    except Exception as e:
        print(f"⚠️ تنبيه أثناء مطابقة التدويرات: {e}", flush=True)

    print("🚀 بدء الاستماع اللحظي عبر WebSocket...", flush=True)
    asyncio.run(run_websocket())

if __name__ == "__main__":
    start_stream()
