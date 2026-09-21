import os
import sys
import time
from datetime import datetime
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# -------------------------------------------------------------------
# 1. إعداد المتغيرات وملف الإعدادات (Config Engine)
# -------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

PAPER_TRADING = True 

WATCHLIST = [
    "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "MARK", "CYN", "MULN", "PLTR", "BZFD", "QNST", 
    "SHIP", "CWCO", "BNAI", "AISP", "SNDL", "KULR",
    "RIG", "GTEC", "RETO", "PDSB", "AMIX", "DAIC"
]

TRADE_AMOUNT_USD = 50.0       # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 0.5          # النسبة الأدنى للارتفاع %
MIN_VOLUME = 100000           # الحد الأدنى لحجم التداول
MAX_SPREAD_PCT = 0.8          # الحد الأقصى المسموح للفارق بين السعرين
STOP_LOSS_PCT = 0.03          # نسبة وقف الخسارة (3%)
TAKE_PROFIT_PCT = 0.06        # نسبة جني الأرباح (6%)

# -------------------------------------------------------------------
# 2. دالة إرسال التوصيات بالتنسيق التفصيلي المعتمد
# -------------------------------------------------------------------
def send_telegram_recommendation(symbol, company_name, price, change_percent, volume):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    import requests

    # حساب المستويات الفنية
    target_1 = round(price * 1.10, 2)   # الهدف الأول (+10%)
    target_2 = round(price * 1.25, 2)   # الهدف الثاني (+25%)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2) # وقف الخسارة (-3%)

    message = (
        f"🟢 <b>فرصة تداول مكتشفة تلقائياً</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> {symbol} ({company_name})\n"
        f"⚡ <b>اتجاه الصفقة:</b> شراء (اختراق وزخم)\n"
        f"⏱ <b>الإطار الزمني:</b> لحظي / يومي\n"
        f"💰 <b>نطاق سعر ووقت الدخول:</b> ${price:.2f} | مسح آلي\n\n"
        f"📊 <b>التغير اليومي:</b> +{change_percent:.2f}%\n"
        f"📈 <b>حجم التداول:</b> {volume:,}\n\n"
        f"🎯 <b>الهدف الأول:</b> ${target_1:.2f}\n"
        f"🎯 <b>الهدف الثاني:</b> ${target_2:.2f}\n"
        f"🎯 <b>الهدف الثالث:</b> غير محدد\n\n"
        f"🛑 <b>سعر وقف الخسارة:</b> ${stop_loss:.2f}\n"
        f"⏳ <b>وقت الخروج المقترح:</b> عند تحقق الهدف أو كسر وقف الخسارة"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"فشل إرسال توصية تليجرام: {e}")

# -------------------------------------------------------------------
# 3. إدارة المراكز المفتوحة والتقييم الآلي للخروج (Exit Engine)
# -------------------------------------------------------------------
def manage_open_positions(client):
    try:
        positions = client.get_all_positions()
        for pos in positions:
            symbol = pos.symbol
            current_price = float(pos.current_price)
            unrealized_plpc = float(pos.unrealized_plpc)

            # شرط وقف الخسارة (-3%)
            if unrealized_plpc <= -STOP_LOSS_PCT:
                print(f"🚨 تفعيل وقف الخسارة لـ {symbol} عند {unrealized_plpc*100:.2f}%")
                client.close_position(symbol)

            # شرط جني الأرباح (+6%)
            elif unrealized_plpc >= TAKE_PROFIT_PCT:
                print(f"🎯 تفعيل جني الأرباح لـ {symbol} عند {unrealized_plpc*100:.2f}%")
                client.close_position(symbol)

    except Exception as e:
        print(f"خطأ أثناء إدارة المراكز المفتوحة: {e}")

# -------------------------------------------------------------------
# 4. دالة تنفيذ عمليات التداول
# -------------------------------------------------------------------
def execute_trade(client, symbol, entry_price, bid_price, ask_price):
    try:
        account = client.get_account()
        buying_power = float(account.buying_power)
        
        if buying_power < 10:
            return False

        # Spread Filter
        if ask_price > 0 and bid_price > 0:
            spread_pct = ((ask_price - bid_price) / ask_price) * 100
            if spread_pct > MAX_SPREAD_PCT:
                return False

        trade_amount = min(TRADE_AMOUNT_USD, buying_power)
        qty = int(trade_amount / entry_price)
        
        if qty < 1:
            return False

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

    if client:
        manage_open_positions(client)

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="5m")
            
            if df.empty:
                continue

            current_price = df['Close'].iloc[-1]
            open_price = df['Open'].iloc[0]
            current_volume = df['Volume'].sum()
            
            # جلب اسم الشركة
            company_name = ticker.info.get('shortName', symbol)

            info = ticker.fast_info
            bid_price = info.get('lastPrice', current_price)
            ask_price = info.get('lastPrice', current_price)

            change_percent = ((current_price - open_price) / open_price) * 100

            # شروط الدخول
            if change_percent >= MIN_CHANGE_PCT and current_volume >= MIN_VOLUME:
                print(f"🎯 فرصة مكتشفة على {symbol}: ارتفاع {change_percent:.2f}%")
                
                # إرسال التوصية للتليجرام بالتنسيق التفصيلي الأصلي
                send_telegram_recommendation(symbol, company_name, current_price, change_percent, current_volume)
                
                # تنفيذ الصفقة في Alpaca
                if client:
                    execute_trade(client, symbol, current_price, bid_price, ask_price)

        except Exception as e:
            print(f"خطأ أثناء معالجة السهم {symbol}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اكتمل المسح بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
    sys.exit(0)