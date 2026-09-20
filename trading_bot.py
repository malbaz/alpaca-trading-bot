import os
import sys
import time
from datetime import datetime
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# -------------------------------------------------------------------
# 1. إعداد المتغيرات وملف الإعدادات (Config Engine)
# -------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

PAPER_TRADING = False 

# قائمة الأسهم المعتمدة
WATCHLIST = [
    "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "MARK", "CYN", "MULN", "PLTR", "BZFD", "QNST", 
    "SHIP", "CWCO", "BNAI", "AISP", "SNDL", "KULR",
    "RIG", "GTEC", "RETO", "PDSB"
]

# معايير التداول والمخاطرة (Risk Parameters)
TRADE_AMOUNT_USD = 50.0       # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 4.0          # النسبة الأدنى للارتفاع %
MIN_VOLUME = 100000           # الحد الأدنى لحجم التداول
MAX_SPREAD_PCT = 0.8          # الحد الأقصى المسموح للفرق بين السعرين (Bid-Ask Spread %)
STOP_LOSS_PCT = 0.03          # نسبة وقف الخسارة (3%)
TAKE_PROFIT_PCT = 0.06        # نسبة جني الأرباح (6%)

# -------------------------------------------------------------------
# 2. دالة إرسال تنبيهات تليجرام
# -------------------------------------------------------------------
def send_telegram_alert(symbol, price, change_percent, volume, action="SCAN"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    import requests
    message = (
        f"🤖 <b>تنبيه من بوت التداول الذكي</b>\n\n"
        f"📌 <b>السهم:</b> {symbol}\n"
        f"💵 <b>السعر:</b> ${price:.2f}\n"
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
# 3. إدارة المراكز المفتوحة والتقييم الآلي للخروج (Exit Engine)
# -------------------------------------------------------------------
def manage_open_positions(client):
    try:
        positions = client.get_all_positions()
        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            entry_price = float(pos.avg_entry_price)
            current_price = float(pos.current_price)
            unrealized_plpc = float(pos.unrealized_plpc)

            print(f"🔄 متابعة المركز المفتوح {symbol}: الدخول ${entry_price:.2f} | الحالي ${current_price:.2f} | الربح/الخسارة: {unrealized_plpc*100:.2f}%")

            # شرط وقف الخسارة (Stop Loss)
            if unrealized_plpc <= -STOP_LOSS_PCT:
                print(f"🚨 تفعيل وقف الخسارة لـ {symbol} عند {unrealized_plpc*100:.2f}%")
                client.close_position(symbol)
                send_telegram_alert(symbol, current_price, unrealized_plpc*100, 0, action="إغلاق حماية (Stop Loss)")

            # شرط جني الأرباح (Take Profit)
            elif unrealized_plpc >= TAKE_PROFIT_PCT:
                print(f"🎯 تفعيل جني الأرباح لـ {symbol} عند {unrealized_plpc*100:.2f}%")
                client.close_position(symbol)
                send_telegram_alert(symbol, current_price, unrealized_plpc*100, 0, action="إغلاق جني أرباح (Take Profit)")

    except Exception as e:
        print(f"خطأ أثناء إدارة المراكز المفتوحة: {e}")

# -------------------------------------------------------------------
# 4. دالة تنفيذ عمليات التداول مع Idempotency وSpread Filter
# -------------------------------------------------------------------
def execute_trade(client, symbol, entry_price, bid_price, ask_price):
    try:
        account = client.get_account()
        buying_power = float(account.buying_power)
        
        if buying_power < 10:
            print(f"السيولة غير كافية للتداول (${buying_power:.2f})")
            return False

        # فلتر الفرق بين سعر الشراء والبيع (Spread Filter)
        if ask_price > 0 and bid_price > 0:
            spread_pct = ((ask_price - bid_price) / ask_price) * 100
            if spread_pct > MAX_SPREAD_PCT:
                print(f"تجاوز {symbol}: الفارق بين السعرين مرتفع ({spread_pct:.2f}% > {MAX_SPREAD_PCT}%)")
                return False

        trade_amount = min(TRADE_AMOUNT_USD, buying_power)
        qty = int(trade_amount / entry_price)
        
        if qty < 1:
            print(f"سعر السهم ${entry_price} أكبر من الميزانية المخصصة.")
            return False

        # إنشاء معرف فريد للطلب لمنع التكرار (Client Order ID / Idempotency)
        unique_client_order_id = f"bot_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=round(entry_price, 2),
            client_order_id=unique_client_order_id
        )
        
        client.submit_order(request=order_data)
        print(f"تم إرسال أمر شراء محدد لـ {symbol}: {qty} أسهم | معرف الطلب: {unique_client_order_id}")
        send_telegram_alert(symbol, entry_price, 0, 0, action=f"شراء محدد ({qty} سهم)")
        return True

    except Exception as e:
        print(f"خطأ أثناء تنفيذ صفقة {symbol}: {e}")
        return False

# -------------------------------------------------------------------
# 5. دالة المسح الرئيسية
# -------------------------------------------------------------------
def run_trading_bot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] بدء تشغيل محرك التداول الذكي...")

    client = None
    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)

    # 1. إدارة الصفقات المفتوحة أولاً (Stop Loss / Take Profit)
    if client:
        manage_open_positions(client)

    # 2. مسح السوق واكتشاف الفرص
    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="5m")
            
            if df.empty:
                continue

            current_price = df['Close'].iloc[-1]
            open_price = df['Open'].iloc[0]
            current_volume = df['Volume'].sum()
            
            # جلب أسعار العرض والطلب للفلترة
            info = ticker.fast_info
            bid_price = info.get('lastPrice', current_price)
            ask_price = info.get('lastPrice', current_price)

            change_percent = ((current_price - open_price) / open_price) * 100

            # شروط الدخول الذكية
            if change_percent >= MIN_CHANGE_PCT and current_volume >= MIN_VOLUME:
                print(f"🎯 فرصة مكتشفة على {symbol}: ارتفاع {change_percent:.2f}% | الحجم: {current_volume}")
                if client:
                    execute_trade(client, symbol, current_price, bid_price, ask_price)
            else:
                print(f"تجاوز {symbol}: التغير {change_percent:.2f}% (لا يطابق الشروط)")

        except Exception as e:
            print(f"خطأ أثناء معالجة السهم {symbol}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اكتمل المسح وبحث المراقبة بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
    sys.exit(0)
