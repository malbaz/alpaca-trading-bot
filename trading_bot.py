import os
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ---------------------------------------------------------
# 1. الإعدادات والمعايير السريعة للتداول الخاطف (Fast Scalp & Rotation)
# ---------------------------------------------------------

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ضبط وضع التجربة
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# قائمة الأسهم المحدثة (الشرعية وتحت $16)
WATCHLIST = [
    "ONCY", "ABVC", "LRHC", "TLSI", "DBRG",
    "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV", 
    "CYN", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "KULR", "RIG", "GTEC", "RETO", "PDSB", "JAGX", "GRML", 
    "BFLY", "EAF", "IPDN", "WFCF", "CPOP", "LGHL"
]

TRADE_AMOUNT_USD = 100.0      # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 5.0          # رفع شرط الارتفاع إلى +5% لاقتناص الأسهم السريعة فقط
MIN_VOLUME = 250000           # رفع شرط السيولة إلى 250 ألف سهم لتجنب الأسهم البطئية
MAX_SPREAD_PCT = 0.8          # الحد الأقصى للسبريد %

# أهداف الخروج السريع جداً والتدوير
QUICK_TAKE_PROFIT_PCT = 0.030 # هدف سريع جداً لتأمين الربح اللحظي (+3.0%)
MAX_TAKE_PROFIT_PCT = 0.070   # الهدف الأقصى عند استمرار الزخم (+7.0%)
STOP_LOSS_PCT = 0.025         # وقف خسارة مشدد لحماية الحساب (-2.5%)

# ---------------------------------------------------------
# 2. دوال التليجرام المساعدة
# ---------------------------------------------------------

def escape_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, price, change_percent, volume, is_extended=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنبيه: بيانات التليجرام مفقودة.")
        return False

    target_fast = round(price * (1 + QUICK_TAKE_PROFIT_PCT), 2)
    target_max = round(price * (1 + MAX_TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
    
    market_phase = "تداول ممتد (Pre/After-Market) 🌙" if is_extended else "الجلسة الرسمية ☀️"

    message_text = (
        f"⚡ <b>صفقة خاطفة سريعة ($100)</b> ({market_phase})\n\n"
        f"📌 <b>رمز السهم:</b> <code>{escape_html(symbol)}</code>\n"
        f"🔥 <b>حالة السهم:</b> زخم عالي وسرعة حركة\n"
        f"💵 <b>حجم الصفقة:</b> ${TRADE_AMOUNT_USD:.0f}\n"
        f"🎯 <b>سعر الدخول:</b> ${price:.2f}\n\n"
        f"📊 <b>التغير اللحظي:</b> +{change_percent:.2f}%\n"
        f"⚡ <b>السيولة والنشاط:</b> {volume:,}\n\n"
        f"🚀 <b>هدف الخروج الخاطف (+3.0%):</b> ${target_fast:.2f}\n"
        f"🏆 <b>الهدف الممتد (+7.0%):</b> ${target_max:.2f}\n"
        f"🛑 <b>وقف الخسارة المشدد (-2.5%):</b> ${stop_loss:.2f}\n"
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
# 3. محرك تنفيذ التداول الخاطف المباشر
# ---------------------------------------------------------

def execute_trade(trading_client, symbol, current_price):
    try:
        # فحص هل نملك مركزاً مفتوحاً حالياً في السهم لتجنب تكرار الأمر في نفس اللحظة
        positions = trading_client.get_all_positions()
        for p in positions:
            if p.symbol == symbol:
                print(f"ℹ️ {symbol} ممتلوك حالياً بانتظار الهدف.")
                return False

        qty = max(1, int(TRADE_AMOUNT_USD / current_price))
        limit_price = round(current_price * 1.005, 2)  # سماحية دخول 0.5% لضمان التنفيذ الفوري

        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=limit_price,
            extended_hours=True
        )

        order = trading_client.submit_order(order_data)
        print(f"✅ Alpaca: تم الشراء الخاطف بقيمة $100 في {symbol} [أمر رقم: {order.id}]")
        return True

    except Exception as e:
        print(f"❌ Alpaca: خطأ تنفيذ صفقة لـ {symbol}: {e}")
        return False

# ---------------------------------------------------------
# 4. محرك إدارة الخروج السريع والدوران (Fast Exit & Re-Entry Logic)
# ---------------------------------------------------------

def manage_open_positions(trading_client):
    """ مراقبة الصفقات وجني الأرباح الخاطفة وتحرير السيولة فوراً """
    try:
        positions = trading_client.get_all_positions()
        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            entry_price = float(pos.avg_entry_price)
            current_price = float(pos.current_price)

            change_pct = (current_price - entry_price) / entry_price

            # 1. الخروج بوقف الخسارة المشدد (-2.5%)
            if change_pct <= -STOP_LOSS_PCT:
                print(f"🚨 خروج سريع من {symbol}: 🛑 وقف خسارة (-2.5%) [السعر: ${current_price:.2f}]")
                exit_order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    limit_price=current_price,
                    extended_hours=True
                )
                trading_client.submit_order(exit_order)

            # 2. الخروج الخاطف بالهدف السريع (+3.0%) أو الممتد (+7.0%)
            elif change_pct >= QUICK_TAKE_PROFIT_PCT:
                reason = "🏆 اقتناص الهدف الممتد (+7.0%)" if change_pct >= MAX_TAKE_PROFIT_PCT else "⚡ جني أرباح خاطف وسريع (+3.0%)"
                print(f"🚨 تفعيل جني الأرباح الخاطف لـ {symbol}: {reason} [السعر: ${current_price:.2f}]")
                exit_order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    limit_price=current_price,
                    extended_hours=True
                )
                trading_client.submit_order(exit_order)

    except Exception as e:
        print(f"⚠️ خطأ أثناء إدارة الصفقات المفتوحة: {e}")

# ---------------------------------------------------------
# 5. الدالة الرئيسية لتشغيل البوت
# ---------------------------------------------------------

def run_trading_bot():
    print(f"🚀 بدء تشغيل محرك التداول الخاطف والدوران السريع (Paper={PAPER_TRADING})...")

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("❌ خطأ: مفاتيح Alpaca غير كافية.")
        return

    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)

    try:
        account = trading_client.get_account()
        print(f"✅ الاتصال ناجح بـ Alpaca | القوة الشرائية: ${account.buying_power}")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Alpaca: {e}")
        return

    # أولاً: جني الأرباح وتحرير المحفظة
    manage_open_positions(trading_client)

    # ثانياً: اقتناص الأسهم الأكثر سيولة وزخماً
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

            # الفلترة الشديدة للسرعة والسيولة
            if change_percent >= MIN_CHANGE_PCT and volume >= MIN_VOLUME and current_price <= 16.0:
                print(f"🔥 فرصة نارية على {symbol}: ارتفاع {change_percent:.2f}% | السيولة: {volume:,}")

                send_telegram_recommendation(symbol, current_price, change_percent, volume, is_extended=True)
                execute_trade(trading_client, symbol, current_price)

        except Exception as e:
            print(f"⚠️ خطأ أثناء فحص السهم {symbol}: {e}")

    print("🏁 اكتمل المسح السريع والتنفيذ بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
