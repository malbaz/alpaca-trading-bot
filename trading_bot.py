import os
import sys
import re
from datetime import datetime
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
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

# الوضع الافتراضي: Paper Trading للأمان. للتداول الحقيقي يحدد المتغير البيئي بـ false
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

WATCHLIST = [
    "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV",
    "MARK", "CYN", "MULN", "PLTR", "BZFD", "QNST", 
    "SHIP", "CWCO", "BNAI", "AISP", "SNDL", "KULR",
    "RIG", "GTEC", "RETO", "PDSB", "DAIC", "AMIX"
]

# الأسهم الاستثمارية اليدوية لاستثنائها من التصفية التلقائية
MANUAL_HOLDINGS = ["AAPL", "NVDA", "AMZN"] 

TRADE_AMOUNT_USD = 50.0       # حجم الصفقة بالدولار
MIN_CHANGE_PCT = 4.0          # النسبة الأدنى للارتفاع %
MIN_VOLUME = 100000           # الحد الأدنى لحجم التداول
MAX_SPREAD_PCT = 0.8          # الحد الأقصى المسموح للفارق بين السعرين
STOP_LOSS_PCT = 0.03          # نسبة وقف الخسارة (3%)
TAKE_PROFIT_PCT = 0.06        # نسبة جني الأرباح (6%)
MAX_OPEN_POSITIONS = 5        # الحد الأقصى للمراكز المفتوحة المتزامنة

# -------------------------------------------------------------------
# 2. تنظيف النصوص وإرسال التليجرام
# -------------------------------------------------------------------
def escape_html(text):
    """تنظيف النصوص لمنع انكسار رسائل HTML في تليجرام"""
    text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_recommendation(symbol, company_name, price, change_percent, volume, qty):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    import requests

    target_1 = round(price * (1 + TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)

    clean_symbol = escape_html(symbol)
    clean_company = escape_html(company_name)

    message = (
        f"🟢 <b>فرصة تداول مكتشفة ومتفاعلة آلياً</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> {clean_symbol} ({clean_company})\n"
        f"⚡ <b>اتجاه الصفقة:</b> شراء (زخم واختراق)\n"
        f"⏱ <b>الإطار الزمني:</b> لحظي / يومي\n"
        f"💰 <b>سعر الدخول:</b> ${price:.2f} | <b>الكمية:</b> {qty} أسهم\n\n"
        f"📊 <b>التغير اليومي:</b> +{change_percent:.2f}%\n"
        f"📈 <b>حجم التداول:</b> {volume:,}\n\n"
        f"🎯 <b>هدف جني الأرباح (+6%):</b> ${target_1:.2f}\n"
        f"🛑 <b>سعر وقف الخسارة (-3%):</b> ${stop_loss:.2f}\n"
        f"⏳ <b>وقت الخروج المقترح:</b> تنفيذ آلي معلق لدى الوسيط (Bracket Order)"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"فشل إرسال توصية تليجرام: {e}")

# -------------------------------------------------------------------
# 3. فحص الـ Spread الحقيقي عبر Alpaca Data API
# -------------------------------------------------------------------
def get_real_spread_and_price(data_client, symbol, yf_price):
    try:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = data_client.get_stock_latest_quote(req)
        
        if symbol not in quotes:
            return None, None, "لا توجد أسعار Quote المباشرة"

        quote = quotes[symbol]
        bid = float(quote.bid_price) if quote.bid_price else 0.0
        ask = float(quote.ask_price) if quote.ask_price else 0.0

        if bid <= 0 or ask <= 0:
            return None, None, "أسعار العرض/الطلب صفرية"

        # الانحراف عن سعر yfinance
        mid_price = (bid + ask) / 2
        dev_pct = abs(mid_price - yf_price) / yf_price * 100
        if dev_pct > 2.0:
            return None, None, f"انحراف السعر عن yfinance كبير ({dev_pct:.2f}%)"

        spread_pct = ((ask - bid) / ask) * 100
        return spread_pct, ask, "OK"

    except Exception as e:
        return None, None, f"خطأ جلب الـ Spread: {e}"

# -------------------------------------------------------------------
# 4. محرك إدارة المراكز الاحتياطي (Safety Net Exit Engine)
# -------------------------------------------------------------------
def manage_open_positions(trading_client):
    try:
        positions = trading_client.get_all_positions()
        for pos in positions:
            symbol = pos.symbol
            
            # استثناء الأسهم طويلة الأجل أو الأسهم خارج Watchlist
            if symbol in MANUAL_HOLDINGS or symbol not in WATCHLIST:
                continue

            unrealized_plpc = float(pos.unrealized_plpc)

            # شبكة أمان فقط إذا لم ينفذ أمر الـ Bracket لدى الوسيط
            if unrealized_plpc <= -STOP_LOSS_PCT or unrealized_plpc >= TAKE_PROFIT_PCT:
                print(f"🚨 تصفية احتياطية للمركز {symbol} عند نسبة: {unrealized_plpc*100:.2f}%")
                trading_client.close_position(symbol)

    except Exception as e:
        print(f"خطأ أثناء إدارة المراكز: {e}")

# -------------------------------------------------------------------
# 5. تنفيذ الشراء الحتمي (Idempotent Bracket Order)
# -------------------------------------------------------------------
def execute_trade(trading_client, data_client, symbol, yf_price, company_name, change_percent, current_volume):
    try:
        account = trading_client.get_account()
        if account.trading_blocked:
            print("الحساب معطل عن التداول.")
            return False

        # فحص عدد المراكز المفتوحة
        positions = trading_client.get_all_positions()
        if len(positions) >= MAX_OPEN_POSITIONS:
            print(f"تم الوصول للحد الأقصى للمراكز المفتوحة ({MAX_OPEN_POSITIONS})")
            return False

        # معرّف حتمي يمنع الشراء المكرر في نفس اليوم
        today_str = datetime.now().strftime('%Y%m%d')
        deterministic_order_id = f"mom-{symbol}-{today_str}"

        # فحص إذا تم إرسال أمر لنفس السهم اليوم
        orders = trading_client.get_orders()
        for o in orders:
            if o.client_order_id == deterministic_order_id:
                print(f"تجاوز {symbol}: يوجد أمر منفذ/معلق مسبقاً لهذا اليوم ({deterministic_order_id})")
                return False

        # فحص الـ Spread الفعلي
        spread_pct, ask_price, status_msg = get_real_spread_and_price(data_client, symbol, yf_price)
        if spread_pct is None:
            print(f"تجاوز {symbol}: {status_msg}")
            return False

        if spread_pct > MAX_SPREAD_PCT:
            print(f"تجاوز {symbol}: الـ Spread مرتفع ({spread_pct:.2f}% > {MAX_SPREAD_PCT}%)")
            return False

        entry_price = ask_price
        buying_power = float(account.buying_power)
        trade_amount = min(TRADE_AMOUNT_USD, buying_power)
        qty = int(trade_amount / entry_price)
        
        if qty < 1:
            print(f"تجاوز {symbol}: المبلغ المخصص لا يكفي لشراء سهم كامل (${entry_price:.2f})")
            return False

        # حساب مستويات الـ Bracket Order
        take_profit_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2)
        stop_loss_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)

        # إرسال أمر Bracket متكامل ينفذ الخروج آلياً لدى الوسيط
        order_request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(entry_price, 2),
            client_order_id=deterministic_order_id,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit_price),
            stop_loss=StopLossRequest(stop_price=stop_loss_price)
        )
        
        trading_client.submit_order(request=order_request)
        print(f"✅ تم إرسال أمر شراء Bracket لـ {symbol}: {qty} أسهم عند ${entry_price:.2f}")

        # إرسال التليجرام بعد نجاح الأمر فقط
        send_telegram_recommendation(symbol, company_name, entry_price, change_percent, current_volume, qty)
        return True

    except Exception as e:
        print(f"خطأ أثناء تنفيذ صفقة {symbol}: {e}")
        return False

# -------------------------------------------------------------------
# 6. المحرك الرئيسي
# -------------------------------------------------------------------
def run_trading_bot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] بدء تشغيل البوت المطور (Paper={PAPER_TRADING})...")

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("مفاتيح Alpaca API غير متوفرة.")
        return

    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=PAPER_TRADING)
    data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    # فحص فتح السوق
    clock = trading_client.get_clock()
    if not clock.is_open:
        print("السوق الأمريكي مغلق حالياً. توقف المسح.")
        return

    # إدارة المراكز المفتوحة أولاً
    manage_open_positions(trading_client)

    # مسح السوق
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
                company_name = ticker.info.get('shortName', symbol) if hasattr(ticker, 'info') else symbol
                execute_trade(trading_client, data_client, symbol, current_price, company_name, change_percent, current_volume)

        except Exception as e:
            print(f"خطأ معالجة السهم {symbol}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اكتمل المسح بنجاح.")

if __name__ == "__main__":
    run_trading_bot()
    sys.exit(0)
