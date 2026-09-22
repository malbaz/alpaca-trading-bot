import os
import sys
from datetime import datetime
import yfinance as yf
import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# -------------------------------------------------------------------
# 1. الإعدادات ومتغيرات البيئة
# -------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ضبط وضع التجربة
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

WATCHLIST = [
    "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "CYN", "PLTR", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "SNDL", "KULR", "RIG", "GTEC", "RETO", "PDSB"
]

TRADE_AMOUNT_USD = 50.0       # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 0.5          # تم ضبطها للاختبار المحلي
MIN_VOLUME = 100000           # الحد الأدنى لحجم التداول
MAX_SPREAD_PCT = 5.0          # تم رفعها للاختبار المحلي
STOP_LOSS_PCT = 0.03          # نسبة وقف الخسارة (3%)
TAKE_PROFIT_PCT = 0.06        # نسبة جني الأرباح (6%)

# -------------------------------------------------------------------
# 2. دالة إرسال التليجرام المستقلة والمباشرة
# -------------------------------------------------------------------
def escape_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, company_name, price, change_percent, volume):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنبيه: بيانات بوت التليجرام (TOKEN/CHAT_ID) مفقودة من Variables/Secrets.")
        return False

    target_1 = round(price * (1 + TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)

    clean_symbol = escape_html(symbol)
    clean_company = escape_html(company_name)

    message = (
        f"🟢 <b>فرصة تداول مكتشفة تلقائياً</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> {clean_symbol} ({clean_company})\n"
        f"⚡ <b>اتجاه الصفقة:</b> شراء (اختراق وزخم)\n"
        f"⏱ <b>الإطار الزمني:</b> لحظي / يومي\n"
        f"💰 <b>نطاق سعر ووقت الدخول:</b> ${price:.2f} | مسح آلي\n\n"
        f"📊 <b>التغير اليومي:</b> +{change_percent:.2f}%\n"
        f"📈 <b>حجم التداول:</b> {volume:,}\n\n"
        f"🎯 <b>الهدف الأول (+6%):</b> ${target_1:.2f}\n"
        f"🎯 <b>الهدف الثاني:</b> ${round(price * 1.10, 2):.2f}\n"
        f"🎯 <b>الهدف الثالث:</b> غير محدد\n\n"
        f"🛑 <b>سعر وقف الخسارة (-3%):</b> ${stop_loss:.2f}\n"
        f"⏳ <b>وقت الخروج المقترح:</b> عند تحقق الهدف أو كسر وقف الخسارة"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, json=payload, timeout=8)
        if response.status_code == 200:
            print(f"✅ تم إرسال إشعار التليجرام بنجاح للسهم: {symbol}")
            return True
        else:
            print(f"❌ فشل إرسال التليجرام لـ {symbol} | الكود: {response.status_code} | الاستجابة: {response.text}")
            return False
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بسيرفر التليجرام: {e}")
        return False

# -------------------------------------------------------------------
# 3. دالة التنفيذ لدى Alpaca المعالجة للأخطاء
# -------------------------------------------------------------------
def execute_trade(trading_client, symbol, yf_price):
    if not trading_client:
        print(f"⏭️ التجاوز عن تنفيذ صفقة {symbol} لدى Alpaca بسبب عدم توفر اتصال معتمد.")
        return False

    try:
        today_str = datetime.now().strftime('%Y%m%d')
        deterministic_order_id = f"mom-{symbol}-{today_str}"

        account = trading_client.get_account()
        buying_power = float(account.buying_power)
        
        qty = int(min(TRADE_AMOUNT_USD, buying_power) / yf_price)
        if qty < 1:
            print(f"⚠️ القوة الشرائية المتاحة لا تكفي لشراء سهم كامل من {symbol}")
            return False

        take_profit_price = round(yf_price * (1 + TAKE_PROFIT_PCT), 2)
        stop_loss_price = round(yf_price * (1 - STOP_LOSS_PCT), 2)

        order_request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(yf_price, 2),
            client_order_id=deterministic_order_id,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit_price),
            stop_loss=StopLossRequest(stop_price=stop_loss_price)
        )
        
        trading_client.submit_order(request=order_request)
        print(f"✅ تم إرسال أمر الشراء بنجاح لـ {symbol} لدى Alpaca.")
        return True

    except Exception as e:
        print(f"❌ خطأ تنفيذ صفقة Alpaca لـ {symbol}: {e}")
        return False

# -------------------------------------------------------------------
# 4. المحرك الرئيسي
# -------------------------------------------------------------------
def run_trading_bot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] بدء تشغيل محرك التداول (Paper={PAPER_TRADING})...")

    trading_client = None
    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        try:
            trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)
            # فحص الاتصال
            acc = trading_client.get_account()
            print(f"✅ تم الاتصال بحساب Alpaca بنجاح | القوة الشرائية: ${acc.buying_power}")
        except Exception as e:
            print(f"❌ فشل التوثيق مع Alpaca (Unauthorized/Key Error): {e}")
            print("💡 تلميح: تأكد أن المفاتيح المضافة في GitHub Secrets تطابق وضع PAPER_TRADING المختار.")
            trading_client = None

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="5m")
            
            if df.empty:
                continue

            current_price = float(df['Close'].iloc[-1])
            open_price = float(df['Open'].iloc[0])
            current_volume = int(df['Volume'].sum())
            change_percent = ((current_price - open_price) / open_price) * 100

            if change_percent >= MIN_CHANGE_PCT and current_volume >= MIN_VOLUME:
                company_name = symbol
                try:
                    company_name = ticker.info.get('shortName', symbol)
                except:
                    pass

                print(f"🎯 فرصة مكتشفة على {symbol}: ارتفاع {change_percent:.2f}%")
                
                # 1. إرسال التليجرام أولاً بشكل مستقل وضمان وصولها
                send_telegram_recommendation(symbol, company_name, current_price, change_percent, current_volume)
                
                # 2. محاولة التنفيذ في Alpaca ثانياً
                execute_trade(trading_client, symbol, current_price)

        except Exception as e:
            print(f"❌ خطأ أثناء معالجة السهم {symbol}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اكتمل المسح بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
    sys.exit(0)
