import os
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# استدعاء متغيرات البيئة الخاصة بتليجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

WATCHLIST = [
    # الأسهم الشرعية المفلترة من منصة سهم (تحت 16$)
    "ONCY", "ABVC", "LRHC", "TLSI", "DKGFHY", "DBRG",
    
    # الأسهم الشرعية المنقاة من قائمتك الحالية (تحت 16$)
    "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV", 
    "CYN", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "KULR", "RIG", "GTEC", "RETO", "PDSB", "JAGX", "GRML", 
    "BFLY", "EAF", "IPDN", "WFCF", "CPOP", "LGHL", "TNMG", "PBM", "ATGL"
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
        "🟢 <b>فرصة تداول مكتشفة تلقائياً (Pre-Market / Regular)</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> <code>{symbol}</code> ({name})\n"
        "⚡ <b>اتجاه الصفقة:</b> شراء (اختراق وزخم)\n"
        "⏱️ <b>الإطار الزمني:</b> لحظي / يومي\n"
        f"💰 <b>نطاق سعر ووقت الدخول:</b> ${entry_price} | مسح آلي\n\n"
        f"📊 <b>التغير الحالي:</b> +{change_percent:.2f}%\n"
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
    """دالة معزولة لتنفيذ التداول الافتراضي تدعم ما قبل السوق (Pre-market)"""
    api_key = os.getenv('ALPACA_API_KEY')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not secret_key:
        print("مفاتيح Alpaca غير مضافة في البيئة.")
        return

    try:
        client = TradingClient(api_key, secret_key, paper=False)
        allocation = 20  # تخصيص 20$ لكل صفقة تجريبية
        qty = max(1, int(allocation / price))
        limit_price = round(price, 2)

        # استخدام أمر محدّد السعر (Limit Order) يدعم الساعات الممتدة (Extended Hours)
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True  # تفعيل التداول في Pre-market
        )
        client.submit_order(order_data=order_data)
        print(f"✅ تم تنفيذ صفقة افتراضية (Pre-market): شراء {qty} سهم في {symbol} بسعر ${limit_price}")
    except Exception as e:
        print(f"⚠️ خطأ في التداول الافتراضي: {e}")

def run_screener():
    print("بدء عملية فحص الأسهم (بما في ذلك Pre-market)...")
    matching_stocks = []

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            # تفعيل prepost=True لقراءة بيانات ما قبل التداول
            hist = ticker.history(period="1d", interval="5m", prepost=True)
            
            if hist.empty or len(hist) < 2:
                continue

            # السعر الحالي والتغير مقارنة بأول شمعة في اليوم
            first_price = hist['Open'].iloc[0]
            current_price = hist['Close'].iloc[-1]
            volume = hist['Volume'].sum()
            
            change_percent = ((current_price - first_price) / first_price) * 100

            # شروط التصفية لخطف الفرص السريعة (تغير >= 2% وحجم تداول مناسب)
            if change_percent >= 2.0 and volume > 10000:
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
            # 2. تنفيذ التداول الوهمي المخصص لـ Pre-market
            execute_paper_trade(stock['symbol'], stock['price'])
    else:
        print("لم يتم العثور على أسهم تطابق الشروط حالياً.")

if __name__ == "__main__":
    run_screener()
