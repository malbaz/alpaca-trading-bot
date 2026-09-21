import os
import sys
from datetime import datetime
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# -------------------------------------------------------------------
# 1. الإعدادات والخيارات (Config Engine)
# -------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# الوضع التجريبي
PAPER_TRADING = True

WATCHLIST = [
    "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "CYN", "PLTR", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "SNDL", "KULR", "RIG", "GTEC", "RETO", "PDSB"
]

MANUAL_HOLDINGS = ["AAPL", "NVDA", "AMZN"] 

TRADE_AMOUNT_USD = 50.0       # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 0.5          # تم خفضها للاختبار
MIN_VOLUME = 100000           # الحد الأدنى لحجم التداول
MAX_SPREAD_PCT = 5.0          # تم رفعها للاختبار
STOP_LOSS_PCT = 0.03          # نسبة وقف الخسارة (3%)
TAKE_PROFIT_PCT = 0.06        # نسبة جني الأرباح (6%)
MAX_OPEN_POSITIONS = 5        

# -------------------------------------------------------------------
# 2. تنظيف النصوص وإرسال التليجرام (مستقلة وتعمل فور رصد الفرصة)
# -------------------------------------------------------------------
def escape_html(text):
    text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, company_name, price, change_percent, volume):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("خطأ: بيانات بوت التليجرام غير مكتملة.")
        return

    import requests

    target_1 = round(price * (1 + TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)

    clean_symbol = escape_html(symbol)
    clean_company = escape_html(company_name)

    message = (
        f"🟢 <b>فرصة تداول مكتشفة تلقائياً</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> {clean_symbol} ({clean_company})\n"
        f"⚡ <b>اتجاه الصفقة:</b> شراء (زخم واختراق)\n"
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
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            print(f"✅ تم إرسال توصية التليجرام بنجاح لـ {symbol}")
        else:
            print(f"فشل إرسال التليجرام ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"خطأ أثناء اتصال التليجرام: {e}")

# -------------------------------------------------------------------
# 3. تنفيذ الشراء في Alpaca
# -------------------------------------------------------------------
def execute_trade(trading_client, data_client, symbol, yf_price, change_percent, current_volume):
    try:
        today_str = datetime.now().strftime('%Y%m%d')
        deterministic_order_id = f"mom-{symbol}-{today_str}"

        # فحص وجود أصل أو أمر سابق
        orders = trading_client.get_orders()
        for o in orders:
            if o.client_order_id == deterministic_order_id:
                print(f"تجاوز تنفيذ {symbol}: يوجد أمر منفذ/معلق اليوم.")
                return False

        account = trading_client.get_account()
        buying_power = float(account.buying_power)
        qty = int(min(TRADE_AMOUNT_USD, buying_power) / yf_price)
        
        if qty < 1:
            print(f"تجاوز تنفيذ {symbol}: السيولة لا تكفي لشراء سهم كامل.")
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
        print(f"✅ تم تنفيذ أمر الشراء لـ {symbol} لدى Alpaca.")
        return True

    except Exception as e:
        print(f"خطأ تنفيذ صفقة Alpaca لـ {symbol}: {e}")
        return False

# -------------------------------------------------------------------
# 4. المحرك الرئيسي
# -------------------------------------------------------------------
def run_trading_bot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] بدء تشغيل البوت...")

    trading_client = None
    data_client = None

    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        try:
            trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)
            data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        except Exception as e:
            print(f"فشل الاتصال بـ Alpaca: {e}")

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
                
                # 1. إرسال التوصية فوراً لقناة التليجرام
                send_telegram_recommendation(symbol, company_name, current_price, change_percent, current_volume)
                
                # 2. تنفيذ الصفقة لدى الوسيط Alpaca
                if trading_client:
                    execute_trade(trading_client, data_client, symbol, current_price, change_percent, current_volume)

        except Exception as e:
            print(f"خطأ معالجة السهم {symbol}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اكتمل المسح بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
    sys.exit(0)