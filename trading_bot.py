import os
import requests
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

# ---------------------------------------------------------
# 1. الإعدادات والتعيين المباشر
# ---------------------------------------------------------

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# التداول الحقيقي المباشر (False = حقيقي / True = تجريبي)
PAPER_TRADING = False

# قائمة الأسهم المفلترة (استبعاد الأسهم الأقل من 1.50$ لمنع الانزلاق السعري)
WATCHLIST = [
    "ONCY", "ABVC", "TLSI", "DBRG", "AMIX", "DAIC", "VEEA", 
    "FTFT", "SOUN", "BBAI", "LUNR", "SERV", "BZFD", "QNST", 
    "SHIP", "CWCO", "BNAI", "AISP", "KULR", "RIG", "GTEC", 
    "PDSB", "GRML", "BFLY", "EAF", "IPDN", "WFCF", "SDEV"
]

TARGET_TRADE_AMOUNT_USD = 100.0 # الميزانية المستهدفة للصفقة
MIN_PRICE = 1.50              # استبعاد الأسهم المنخفضة السعر جداً
MAX_PRICE = 16.00             # السقف الأقصى لسعر السهم
MIN_CHANGE_PCT = 3.5          # نسبة الارتفاع اللحظي المطلوبة %
MIN_VOLUME = 200000           # الحد الأدنى لحجم السيولة

# نسب جني الأرباح ووقف الخسارة
QUICK_TAKE_PROFIT_PCT = 0.045 # هدف سريع خاطف (+4.5%)
MAX_TAKE_PROFIT_PCT = 0.080   # الهدف الممتد (+8.0%)
STOP_LOSS_PCT = 0.035         # وقف خسارة مدروس (-3.5%)

# ---------------------------------------------------------
# 2. إرسال التنبيهات عبر التليجرام بالتنسيق الكامل والأيقونات
# ---------------------------------------------------------

def escape_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, price, change_percent, volume, actual_budget, is_extended=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    target_fast = round(price * (1 + QUICK_TAKE_PROFIT_PCT), 2)
    target_max = round(price * (1 + MAX_TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
    
    market_phase = "تداول ممتد (Pre/After-Market) 🌙" if is_extended else "الجلسة الرسمية ☀️"

    message_text = (
        f"⚡ <b>صفقة خاطفة سريعة (${actual_budget:.2f})</b>\n"
        f"({market_phase})\n\n"
        f"📌 <b>رمز السهم:</b> {escape_html(symbol)}\n"
        f"🔥 <b>حالة السهم:</b> زخم عالي وسرعة حركة\n"
        f"💵 <b>حجم الصفقة:</b> ${actual_budget:.2f}\n"
        f"🎯 <b>سعر الدخول:</b> ${price:.2f}\n\n"
        f"📊 <b>التغير اللحظي:</b> +{change_percent:.2f}%\n"
        f"⚡ <b>السيولة والنشاط:</b> {volume:,}\n\n"
        f"🚀 <b>هدف الخروج الخاطف (+{QUICK_TAKE_PROFIT_PCT*100:.1f}%):</b>\n${target_fast:.2f}\n\n"
        f"🏆 <b>الهدف الممتد (+{MAX_TAKE_PROFIT_PCT*100:.1f}%):</b> ${target_max:.2f}\n\n"
        f"🚨 <b>وقف الخسارة المشدد (-{STOP_LOSS_PCT*100:.1f}%):</b>\n${stop_loss:.2f}\n"
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
# 3. إلغاء الأوامر القديمة المعلقة
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
# 4. تنفيذ الشراء بميزانية ديناميكية
# ---------------------------------------------------------

def execute_trade(trading_client, symbol, current_price):
    try:
        positions = trading_client.get_all_positions()
        for p in positions:
            if p.symbol == symbol:
                print(f"{symbol} مملوك حالياً بانتظار تحقيق الهدف.")
                return False

        account = trading_client.get_account()
        buying_power = float(account.buying_power)
        trade_budget = min(TARGET_TRADE_AMOUNT_USD, buying_power)

        if trade_budget < 15.0:
            print(f"القوة الشرائية غير كافية للتداول: ${buying_power:.2f}")
            return False

        qty = max(1, int(trade_budget / current_price))
        limit_price = round(current_price * 1.002, 2)

        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True
        )

        order = trading_client.submit_order(order_data)
        print(f"Alpaca: تم الشراء بمبلغ ${trade_budget:.2f} (عدد {qty} سهم) في {symbol} بسعر ${limit_price}")
        return True

    except Exception as e:
        print(f"Alpaca: خطأ تنفيذ صفقة لـ {symbol}: {e}")
        return False

# ---------------------------------------------------------
# 5. إدارة الصفقات المفتوحة والبيع الآلي
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

            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="2d", interval="1m", prepost=True)
                current_price = float(df['Close'].iloc[-1]) if not df.empty else float(pos.current_price)
            except Exception:
                current_price = float(pos.current_price)

            change_pct = (current_price - entry_price) / entry_price
            print(f"فحص {symbol}: سعر الدخول ${entry_price:.2f} | اللحظي ${current_price:.2f} | التغير: {change_pct*100:.2f}%")

            if change_pct >= QUICK_TAKE_PROFIT_PCT or change_pct <= -STOP_LOSS_PCT:
                reason = f"وقف خسارة (-{STOP_LOSS_PCT*100:.1f}%)" if change_pct <= -STOP_LOSS_PCT else f"جني أرباح (+{QUICK_TAKE_PROFIT_PCT*100:.1f}%)"
                print(f"🚨 تفعيل الخروج الآلي لـ {symbol}: {reason} [السعر: ${current_price:.2f}]")

                cancel_open_orders_for_symbol(trading_client, symbol)

                sell_limit_price = round(current_price * 0.996, 2) if change_pct <= -STOP_LOSS_PCT else round(current_price, 2)

                exit_order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=sell_limit_price,
                    extended_hours=True
                )
                trading_client.submit_order(exit_order)
                print(f"✅ تم إرسال أمر البيع لـ {symbol} بسعر ${sell_limit_price}")

    except Exception as e:
        print(f"خطأ أثناء إدارة الصفقات المفتوحة: {e}")

# ---------------------------------------------------------
# 6. التشغيل الرئيسي ومسح الفرص
# ---------------------------------------------------------

def run_trading_bot():
    print(f"بدء تشغيل محرك التداول المطور (Paper={PAPER_TRADING})...")

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("خطأ: مفاتيح Alpaca غير كافية.")
        return

    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)

    try:
        account = trading_client.get_account()
        print(f"الاتصال ناجح بـ Alpaca | القوة الشرائية: ${account.buying_power}")
    except Exception as e:
        print(f"فشل الاتصال بـ Alpaca: {e}")
        return

    # 1. إدارة الصفقات المفتوحة أولاً والبيع المباشر فور الوصول للهدف
    manage_open_positions(trading_client)

    # 2. فحص توفر كاش كافي لفتح صفقة جديدة (حد أدنى 15 دولار)
    buying_power = float(account.buying_power)
    if buying_power < 15.0:
        print("السيولة غير كافية لفتح صفقات جديدة.")
        return

    # 3. فحص قائمة الأسهم واقتناص الاختراقات اللحظية
    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="1m", prepost=True)

            if df.empty or len(df) < 10:
                continue

            current_price = float(df['Close'].iloc[-1])
            price_5m_ago = float(df['Close'].iloc[-5])
            volume_sum = int(df['Volume'].iloc[-10:].sum())

            # الفلترة السعرية
            if not (MIN_PRICE <= current_price <= MAX_PRICE):
                continue

            # حساب الزخم اللحظي لآخر 5 دقائق
            instant_momentum_pct = ((current_price - price_5m_ago) / price_5m_ago) * 100

            if instant_momentum_pct >= MIN_CHANGE_PCT and volume_sum >= MIN_VOLUME:
                print(f"🔥 فرصة نارية على {symbol}: اختراق لحظي +{instant_momentum_pct:.2f}% | السيولة: {volume_sum:,}")

                actual_budget = min(TARGET_TRADE_AMOUNT_USD, buying_power)
                send_telegram_recommendation(symbol, current_price, instant_momentum_pct, volume_sum, actual_budget, is_extended=True)
                execute_trade(trading_client, symbol, current_price)
                break

        except Exception as e:
            print(f"خطأ أثناء فحص السهم {symbol}: {e}")

    print("اكتمل المسح والتنفيذ بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
