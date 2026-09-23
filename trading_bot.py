import os
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ---------------------------------------------------------
# 1. الإعدادات ومتغيرات البيئة
# ---------------------------------------------------------

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ضبط وضع التجربة
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# قائمة الأسهم المحدثة (الشرعية وتحت $16)
WATCHLIST = [
    # الأسهم الشرعية المفلترة من منصة سهم
    "ONCY", "ABVC", "LRHC", "TLSI", "DKGFHY", "DBRG",
    # الأسهم الشرعية المنقاة من القائمة الحالية
    "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV", 
    "CYN", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "KULR", "RIG", "GTEC", "RETO", "PDSB", "JAGX", "GRML", 
    "BFLY", "EAF", "IPDN", "WFCF", "CPOP", "LGHL"
]

TRADE_AMOUNT_USD = 50.0       # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 4.0          # الحد الأدنى لنسبة الارتفاع %
MIN_VOLUME = 100000           # الحد الأدنى لحجم التداول
MAX_SPREAD_PCT = 0.8          # الحد الأقصى للسبريد %
STOP_LOSS_PCT = 0.03          # نسبة وقف الخسارة (3%)
TAKE_PROFIT_PCT = 0.06        # نسبة جني الأرباح (6%)

# ---------------------------------------------------------
# 2. دوال التليجرام المساعدة
# ---------------------------------------------------------

def escape_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, price, change_percent, volume, is_extended=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنبيه: بيانات التليجرام مفقودة.")
        return False

    target_1 = round(price * (1 + TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
    
    market_phase = "تداول ممتد (Pre/After-Market) 🌙" if is_extended else "الجلسة الرسمية ☀️"

    message_text = (
        f"🟢 <b>فرصة تداول مكتشفة تلقائياً</b> ({market_phase})\n\n"
        f"📌 <b>رمز السهم:</b> <code>{escape_html(symbol)}</code>\n"
        f"⚡ <b>الاتجاه:</b> شراء (اختراق وزخم)\n"
        f"🎯 <b>نطاق سعر الدخول:</b> ${price:.2f}\n\n"
        f"📊 <b>التغير الحالي:</b> +{change_percent:.2f}%\n"
        f"⚡ <b>حجم التداول:</b> {volume:,}\n\n"
        f"🎯 <b>الهدف الأول (+6%):</b> ${target_1:.2f}\n"
        f"🛑 <b>سعر وقف الخسارة (-3%):</b> ${stop_loss:.2f}\n"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ خطأ إرسال تليجرام: {e}")
        return False

# ---------------------------------------------------------
# 3. محرك تنفيذ التداول الذكي (Extended Hours Engine)
# ---------------------------------------------------------

def execute_trade(trading_client, symbol, current_price):
    try:
        # حساب كمية الأسهم
        qty = max(1, int(TRADE_AMOUNT_USD / current_price))
        limit_price = round(current_price * 1.005, 2)  # سماحية دخول 0.5% لضمان التنفيذ

        # استخدام أمر حدي يدعم التداول الممتد (Pre-Market / After-Hours)
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=limit_price,
            extended_hours=True
        )

        order = trading_client.submit_order(order_data)
        print(f"✅ Alpaca: تم إرسال أمر الشراء المباشر (Extended Hours) لـ {symbol} [أمر رقم: {order.id}]")
        return True

    except Exception as e:
        print(f"❌ Alpaca: خطأ تنفيذ صفقة لـ {symbol}: {e}")
        return False

# ---------------------------------------------------------
# 4. محرك المراقبة والخروج التلقائي (Programmatic Exit Logic)
# ---------------------------------------------------------

def manage_open_positions(trading_client):
    """ مراقبة الصفقات المفتوحة الخروج بـ Target أو Stop Loss حتى في التداول الممتد """
    try:
        positions = trading_client.get_all_positions()
        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            entry_price = float(pos.avg_entry_price)
            current_price = float(pos.current_price)

            change_pct = (current_price - entry_price) / entry_price

            # تحقق من شرط جني الأرباح أو وقف الخسارة
            if change_pct >= TAKE_PROFIT_PCT or change_pct <= -STOP_LOSS_PCT:
                reason = "🎯 جني الأرباح (+6%)" if change_pct >= TAKE_PROFIT_PCT else "🛑 وقف الخسارة (-3%)"
                print(f"🚨 تفعيل الخروج لـ {symbol}: {reason} [السعر الحالي: ${current_price:.2f}]")

                exit_order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    limit_price=current_price,
                    extended_hours=True
                )
                trading_client.submit_order(exit_order)
                print(f"✅ تم إرسال أمر بيع خروج ممتد لـ {symbol}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء مراجعة الصفقات المفتوحة: {e}")

# ---------------------------------------------------------
# 5. الدالة الرئيسية لتشغيل البوت
# ---------------------------------------------------------

def run_trading_bot():
    print(f"[{yf.Utils().get_json}] بدء تشغيل محرك التداول الممتد (Paper={PAPER_TRADING})...")

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("❌ خطأ: مفاتيح Alpaca غير كافية.")
        return

    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)

    try:
        account = trading_client.get_account()
        print(f"✅ تم الاتصال بحساب Alpaca | القوة الشرائية: ${account.buying_power}")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Alpaca: {e}")
        return

    # أولاً: إدارة وتأمين الصفقات المفتوحة
    manage_open_positions(trading_client)

    # ثانياً: فحص القائمة واقتناص الفرص الجديدة
    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="2d", interval="1m", prepost=True)

            if df.empty or len(df) < 2:
                continue

            current_price = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[0])
            volume = int(df['Volume'].sum())

            change_percent = ((current_price - prev_close) / prev_close) * 100

            # تطبيق شروط الدخول والفلترة
            if change_percent >= MIN_CHANGE_PCT and volume >= MIN_VOLUME and current_price <= 16.0:
                print(f"🎯 فرصة مكتشفة على {symbol}: ارتفاع {change_percent:.2f}% | السعر: ${current_price:.2f}")

                # إرسال تنبيه تليجرام
                send_telegram_recommendation(symbol, current_price, change_percent, volume, is_extended=True)

                # تنفيذ الشراء التلقائي
                execute_trade(trading_client, symbol, current_price)

        except Exception as e:
            print(f"⚠️ خطأ أثناء فحص السهم {symbol}: {e}")

    print("🏁 اكتمل المسح والتنفيد بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
