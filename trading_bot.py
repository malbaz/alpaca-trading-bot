import os
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

# ---------------------------------------------------------
# 1. الإعدادات والتعيين المباشر للتداول الحقيقي الممتد
# ---------------------------------------------------------

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ضبط التداول الحقيقي المباشر قاطعاً (False = حقيقي / True = تجريبي)
PAPER_TRADING = False

# قائمة الأسهم الشرعية وتحت $16
WATCHLIST = [
    "ONCY", "ABVC", "LRHC", "TLSI", "DBRG",
    "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV", 
    "CYN", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "KULR", "RIG", "GTEC", "RETO", "PDSB", "JAGX", "GRML", 
    "BFLY", "EAF", "IPDN", "WFCF", "CPOP", "LGHL"
]

TRADE_AMOUNT_USD = 100.0      # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 4.0          # الحد الأدنى للارتفاع %
MIN_VOLUME = 150000           # الحد الأدنى لحجم التداول

# أهداف الخروج السريع والتنفيذ الممتد
QUICK_TAKE_PROFIT_PCT = 0.030 # هدف سريع خاطف (+3.0%)
MAX_TAKE_PROFIT_PCT = 0.070   # الهدف الأقصى (+7.0%)
STOP_LOSS_PCT = 0.025         # وقف خسارة مشدد (-2.5%)

# ---------------------------------------------------------
# 2. دوال التليجرام
# ---------------------------------------------------------

def escape_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, price, change_percent, volume, is_extended=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    target_fast = round(price * (1 + QUICK_TAKE_PROFIT_PCT), 2)
    target_max = round(price * (1 + MAX_TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
    
    market_phase = "تداول ممتد (Pre/After-Market)" if is_extended else "الجلسة الرسمية"

    message_text = (
        f"صفقة خاطفة حقيقية ($100) ({market_phase})\n\n"
        f"رمز السهم: <code>{escape_html(symbol)}</code>\n"
        f"حجم الصفقة: ${TRADE_AMOUNT_USD:.0f}\n"
        f"سعر الدخول: ${price:.2f}\n\n"
        f"التغير اللحظي: +{change_percent:.2f}%\n"
        f"حجم التداول: {volume:,}\n\n"
        f"هدف الخروج الخاطف (+3.0%): ${target_fast:.2f}\n"
        f"الهدف الممتد (+7.0%): ${target_max:.2f}\n"
        f"وقف الخسارة (-2.5%): ${stop_loss:.2f}\n"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text, "parse_mode": "HTML"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"خطأ إرسال تليجرام: {e}")
        return False

# ---------------------------------------------------------
# 3. دالة إلغاء الأوامر المعلقة القديمة لتحرير الأسهم
# ---------------------------------------------------------

def cancel_open_orders_for_symbol(trading_client, symbol):
    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        open_orders = trading_client.get_orders(req)
        for order in open_orders:
            trading_client.cancel_order_by_id(order.id)
            print(f"تم إلغاء الأمر المعلق السابق {order.id} للسهم {symbol}")
    except Exception as e:
        print(f"خطأ أثناء إلغاء الأوامر المعلقة لـ {symbol}: {e}")

# ---------------------------------------------------------
# 4. محرك تنفيذ الشراء المباشر
# ---------------------------------------------------------

def execute_trade(trading_client, symbol, current_price):
    try:
        positions = trading_client.get_all_positions()
        for p in positions:
            if p.symbol == symbol:
                print(f"{symbol} مملوك حالياً بانتظار تحقيق الهدف.")
                return False

        qty = max(1, int(TRADE_AMOUNT_USD / current_price))
        limit_price = round(current_price * 1.005, 2)

        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True
        )

        order = trading_client.submit_order(order_data)
        print(f"Alpaca (حقيقي): تم الشراء بـ $100 في {symbol} [أمر رقم: {order.id}]")
        return True

    except Exception as e:
        print(f"Alpaca: خطأ تنفيذ صفقة لـ {symbol}: {e}")
        return False

# ---------------------------------------------------------
# 5. محرك إدارة الخروج المباشر والبيع الآلي خارج أوقات السوق الرسمية
# ---------------------------------------------------------

def manage_open_positions(trading_client):
    try:
        positions = trading_client.get_all_positions()
        if not positions:
            print("لا توجد مراكز مفتوحة حالياً للبيع.")
            return

        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            entry_price = float(pos.avg_entry_price)

            # جلب السعر اللحظي الفلي عبر yfinance لضمان دقة أسعار Pre-Market
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="2d", interval="1m", prepost=True)
                if not df.empty:
                    current_price = float(df['Close'].iloc[-1])
                else:
                    current_price = float(pos.current_price)
            except Exception:
                current_price = float(pos.current_price)

            change_pct = (current_price - entry_price) / entry_price
            print(f"فحص المركز {symbol}: سعر الدخول ${entry_price:.2f} | السعر اللحظي ${current_price:.2f} | التغير: {change_pct*100:.2f}%")

            # شرط الخروج عند تحقيق الربح (+3.0%) أو وقف الخسارة (-2.5%)
            if change_pct >= QUICK_TAKE_PROFIT_PCT or change_pct <= -STOP_LOSS_PCT:
                reason = "وقف خسارة (-2.5%)" if change_pct <= -STOP_LOSS_PCT else ("الهدف الممتد (+7.0%)" if change_pct >= MAX_TAKE_PROFIT_PCT else "جني أرباح خاطف (+3.0%)")
                print(f"🚨 تفعيل الخروج المباشر الآلي لـ {symbol}: {reason} [السعر اللحظي: ${current_price:.2f}]")

                # 1. إلغاء أي أمر معلق قديم يمنع البيع
                cancel_open_orders_for_symbol(trading_client, symbol)

                # 2. تحديد سعر البيع المباشر الممتد
                sell_limit_price = round(current_price * 0.995, 2) if change_pct <= -STOP_LOSS_PCT else round(current_price, 2)

                exit_order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=sell_limit_price,
                    extended_hours=True
                )
                trading_client.submit_order(exit_order)
                print(f"✅ تم إرسال أمر البيع المباشر الممتد لـ {symbol} بسعر ${sell_limit_price}")

    except Exception as e:
        print(f"خطأ أثناء إدارة الصفقات المفتوحة: {e}")

# ---------------------------------------------------------
# 6. الدالة الرئيسية لتشغيل البوت
# ---------------------------------------------------------

def run_trading_bot():
    print(f"بدء تشغيل محرك التداول الحقيقي المباشر (Paper={PAPER_TRADING})...")

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("خطأ: مفاتيح Alpaca غير كافية.")
        return

    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)

    try:
        account = trading_client.get_account()
        print(f"الاتصال ناجح بـ Alpaca | القوة الشرائية الحقيقية: ${account.buying_power}")
    except Exception as e:
        print(f"فشل الاتصال بـ Alpaca: {e}")
        return

    # أولاً: تشغيل محرك إدارة الصفقات والبيع المباشر أولاً وبدون شروط على حالة السوق
    manage_open_positions(trading_client)

    # ثانياً: فحص حالة السوق لشراء صفقات جديدة فقط
    try:
        clock = trading_client.get_clock()
        if not clock.is_open:
            print("ملاحظة: الجلسة الرسمية مغلقة. تم إنجاز بيع الصفقات المستهدفة ولن يتم فتح شراء لأسهم جديدة خارج ساعات الجلسة.")
            return
    except Exception as e:
        print(f"ملاحظة عند فحص ساعة السوق: {e}")

    # ثالثاً: فحص القائمة واقتناص الصفقات الجديدة أثناء عمل السوق
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

            if change_percent >= MIN_CHANGE_PCT and volume >= MIN_VOLUME and current_price <= 16.0:
                print(f"فرصة على {symbol}: ارتفاع {change_percent:.2f}% | السيولة: {volume:,}")

                send_telegram_recommendation(symbol, current_price, change_percent, volume, is_extended=True)
                execute_trade(trading_client, symbol, current_price)

        except Exception as e:
            print(f"خطأ أثناء فحص السهم {symbol}: {e}")

    print("اكتمل المسح والتنفيذ بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
