import os
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# استدعاء متغيرات البيئة الخاصة بتليجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# قائمة استرشادية لأسهم السمول كاب للمسح
WATCHLIST = [
    "AMIX", "ADXN", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "MARK", "CYN", "MULN", "PLTR", "SASI", "BZFD", "JEM"
]

def send_telegram_alert(symbol, name, price, volume, change_percent):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("خطأ: مفاتيح تليجرام غير مضافة في البيئة.")
        return

    entry_price = round(price, 2)
    tp1 = round(entry_price * 1.10, 2)
    tp2 = round(entry_price * 1.25, 2)
    sl = round(entry_price * 0.93, 2)

    message_text = (
        "🟢 <b>فرصة تداول مكتشفة تلقائياً</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> <code>{symbol}</code> ({name})\n"
        "⚡ <b>اتجاه الصفقة:</b> شراء (اختراق وزخم)\n"
        "⏱️ <b>الإطار الزمني:</b> لحظي / يومي\n"
        f"💰 <b>نطاق سعر ووقت الدخول:</b> ${entry_price} | مسح آلي\n\n"
        f"📊 <b>التغير اليومي:</b> +{change_percent:.2f}%\n"
        f"📈 <b>حجم التداول:</b> {volume:,}\n\n"
        f"🎯 <b>الهدف الأول:</b> ${tp1}\n"
        f"🎯 <b>الهدف الثاني:</b> ${tp2}\n"
        "🎯 <b>الهدف الثالث:</b> غير محدد\n\n"
        f"🛑 <b>سعر وقف الخسارة:</b> ${sl}\n"
        "⏳ <b>وقت الخروج المقترح:</b> عند تحقق الهدف أو كسر وقف الخسارة"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML"
    }
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"تم إرسال التنبيه للسهم {symbol} بنجاح.")
        else:
            print(f"فشل إرسال التنبيه: {res.text}")
    except Exception as e:
        print(f"خطأ أثناء الاتصال بتليجرام: {e}")

def execute_paper_trade(symbol, price):
    """دالة معزولة لتنفيذ التداول الافتراضي على Alpaca"""
    api_key = os.getenv('ALPACA_API_KEY')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not secret_key:
        print("مفاتيح Alpaca غير مضافة في البيئة.")
        return

    try:
        client = TradingClient(api_key, secret_key, paper=True)
        allocation = 20  # تخصيص 20$ لكل صفقة تجريبية
        qty = max(1, int(allocation / price))

        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        client.submit_order(order_data=order_data)
        print(f"✅ تم تنفيذ صفقة افتراضية: شراء {qty} سهم في {symbol}")
    except Exception as e:
        # خطأ التداول الوهمي لا يوقف البرامج ولا يعطل إرسال القروب
        print(f"⚠️ خطأ في التداول الافتراضي: {e}")

def run_screener():
    print("بدء عملية فحص الأسهم...")
    matching_stocks = []

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d")
            
            if len(hist) < 2:
                continue

            prev_close = hist['Close'].iloc[-2]
            current_price = hist['Close'].iloc[-1]
            volume = hist['Volume'].iloc[-1]
            
            change_percent = ((current_price - prev_close) / prev_close) * 100

            # شروط التصفية (ارتفاع أكثر من 3% وحجم تداول مناسب)
            if change_percent >= 3.0 and volume > 100000:
                name = ticker.info.get('shortName', symbol)
                matching_stocks.append({
                    'symbol': symbol,
                    'name': name,
                    'price': current_price,
                    'volume': volume,
                    'change_percent': change_percent
                })
        except Exception as e:
            print(f"خطأ أثناء فحص {symbol}: {e}")

    if matching_stocks:
        for stock in matching_stocks:
            # 1. إرسال التنبيه للقروب أولاً
            send_telegram_alert(
                stock['symbol'], stock['name'], stock['price'], stock['volume'], stock['change_percent']
            )
            # 2. تنفيذ التداول الوهمي في المسار المعزول
            execute_paper_trade(stock['symbol'], stock['price'])
    else:
        print("لم يتم العثور على أسهم تطابق الشروط حالياً.")

if __name__ == "__main__":
    run_screener()
