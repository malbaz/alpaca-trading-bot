import os
import sys
import time
from datetime import datetime
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# -------------------------------------------------------------------
# 1. إعداد المتغيرات وبيئة العمل
# -------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# استخدام التداول الحقيقي
PAPER_TRADING = False 

# قائمة الأسهم العشرين المعتمدة للمسح والتداول
WATCHLIST = [
    "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "MARK", "CYN", "MULN", "PLTR", 
"BZFD", "QNST", 
    "SHIP", "CWCO", "BNAI", "AISP", "SNDL", "KULR",
    "RIG", "GTEC", "RETO", "PDSB", "DAIC"
]

# -------------------------------------------------------------------
# 2. دالة إرسال تنبيهات تليجرام
# -------------------------------------------------------------------
def send_telegram_alert(symbol, price, change_percent, volume, action="SCAN"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("تنبيه: مفاتيح تليجرام غير مضافة في بيئة العمل.")
        return

    import requests
    message = (
        f"🤖 <b>تنبيه من بوت التداول الآلي</b>\n\n"
        f"📌 <b>السهم:</b> {symbol}\n"
        f"💵 <b>السعر الحالي:</b> ${price:.2f}\n"
        f"📈 <b>التغير:</b> {change_percent:.2f}%\n"
        f"📊 <b>الحجم:</b> {volume:,}\n"
        f"⚡ <b>الإجراء:</b> {action}"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"فشل إرسال تنبيه تليجرام: {e}")

# -------------------------------------------------------------------
# 3. دالة تنفيذ عمليات التداول عبر Alpaca
# -------------------------------------------------------------------
def execute_trade(symbol, entry_price):
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("خطأ: مفاتيح Alpaca API غير متوفرة.")
        return False

    try:
        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)
        account = client.get_account()
        
        # التأكد من توفر السيولة النقدية (حد أدنى $10)
        buying_power = float(account.buying_power)
        if buying_power < 10:
            print(f"السيولة غير كافية للتداول (${buying_power:.2f})")
            return False

        # حساب الكمية المستهدفة بمبلغ تقريبي $50 أو السيولة المتاحة
        trade_amount = min(50.0, buying_power)
        qty = int(trade_amount / entry_price)
        
        if qty < 1:
            print(f"سعر السهم ${entry_price} أكبر من القدرة الشرائية المخصصة.")
            return False

        # إعداد أمر الشراء المحدد
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=round(entry_price, 2)
        )
        
        trade = client.submit_order(request=order_data)
        print(f"تم إرسال أمر شراء محدد لـ {symbol}: {qty} أسهم بسعر ${entry_price:.2f}")
        send_telegram_alert(symbol, entry_price, 0, 0, action=f"شراء محدد ({qty} سهم)")
        return True

    except Exception as e:
        print(f"خطأ أثناء تنفيذ صفقة {symbol}: {e}")
        return False

# -------------------------------------------------------------------
# 4. دالة المسح الرئيسية مع الخروج المحدد
# -------------------------------------------------------------------
def run_trading_bot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] بدء تشغيل مسح السوق والتداول...")
    
    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="5m")
            
            if df.empty:
                continue

            current_price = df['Close'].iloc[-1]
            open_price = df['Open'].iloc[0]
            current_volume = df['Volume'].sum()
            
            change_percent = ((current_price - open_price) / open_price) * 100

            # شروط الدخول البرمجية (ارتفاع > 4% وحجم تداول مناسب)
            if change_percent >= 4.0 and current_volume > 100000:
                print(f"🎯 إشارة مكتشفة على {symbol}: ارتفاع {change_percent:.2f}% | الحجم: {current_volume}")
                execute_trade(symbol, current_price)
                send_telegram_alert(symbol, current_price, change_percent, current_volume, action="فرصة شراء متطابقة")
            else:
                print(f"تجاوز {symbol}: التغير {change_percent:.2f}% (لا يطابق الشروط)")

        except Exception as e:
            print(f"خطأ أثناء معالجة السهم {symbol}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اكتمل المسح بنجاح، إغلاق المهمة.")

if __name__ == "__main__":
    run_trading_bot()
    sys.exit(0)
