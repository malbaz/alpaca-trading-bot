import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest

load_dotenv(override=True)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip().strip('"')
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

def send_telegram_msg(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram Error:", e)

def get_date_range(days_back=120):
    today = datetime.now().date()
    start_date = today - timedelta(days=days_back)
    return start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return 0.5
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    return round(sum(tr_list[-period:]) / period, 2)

def detect_candlestick_pattern(opens, highs, lows, closes):
    if len(closes) < 2:
        return "بيانات غير كافية"
    o1, c1 = opens[-2], closes[-2]
    o2, h2, l2, c2 = opens[-1], highs[-1], lows[-1], closes[-1]
    body = abs(c2 - o2)
    candle_range = h2 - l2
    
    if o1 > c1 and c2 > o2 and o2 <= c1 and c2 >= o1:
        return "شمعة ابتلاعية صاعدة (Bullish Engulfing)"
    if candle_range > 0 and (min(o2, c2) - l2) >= (2 * body) and (h2 - max(o2, c2)) <= (0.2 * candle_range):
        return "شمعة مطرقة انعكاسية (Hammer)"
    if c2 > o2:
        return "شمعة صاعدة عادية"
    elif c2 < o2:
        return "شمعة هابطة"
    else:
        return "شمعة دوجي محايدة"

def get_market_trend():
    start_d, end_d = get_date_range(60)
    url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/day/{start_d}/{end_d}?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}"
    try:
        res = requests.get(url).json()
        results = res.get("results", [])
        if len(results) >= 20:
            closes = [item["c"] for item in reversed(results)]
            ema20 = sum(closes[-20:]) / 20
            return "صعودي (SPY أعلى من EMA20)" if closes[-1] >= ema20 else "هابط (SPY أسفل EMA20)"
    except Exception as e:
        print("Market Trend Error:", e)
    return "غير محدد"

def get_stock_metrics(symbol):
    start_d, end_d = get_date_range(120)
    url_hist = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_d}/{end_d}?adjusted=true&sort=desc&limit=100&apiKey={POLYGON_API_KEY}"
    res_hist = requests.get(url_hist).json()
    
    results = res_hist.get("results", [])
    if not results or len(results) < 20:
        return None

    results_sorted = list(reversed(results))
    opens = [item["o"] for item in results_sorted]
    closes = [item["c"] for item in results_sorted]
    volumes = [item["v"] for item in results_sorted]
    lows = [item["l"] for item in results_sorted]
    highs = [item["h"] for item in results_sorted]

    close_price = closes[-1]
    rsi = calculate_rsi(closes)
    ema20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)
    
    if len(closes) >= 50:
        ema50 = round(sum(closes[-50:]) / 50, 2)
        ema50_str = f"${ema50}"
    else:
        ema50 = None
        ema50_str = "غير متوفر (البيانات أقل من 50 يوماً)"
    
    atr = calculate_atr(highs, lows, closes)
    current_volume = int(round(volumes[-1]))
    avg_volume = int(round(sum(volumes[-20:]) / min(len(volumes), 20)))
    
    support_level = min(lows[-20:])
    resistance_level = max(highs[-20:])

    pattern = detect_candlestick_pattern(opens, highs, lows, closes)

    if rsi < 30:
        rsi_description = f"{rsi} (ذروة بيع صريحة أدنى من 30)"
    elif rsi > 70:
        rsi_description = f"{rsi} (ذروة شراء صريحة أعلى من 70)"
    else:
        rsi_description = f"{rsi} (منطقة محايدة)"

    if ema50 is not None:
        trend_description = "صعودي على المتوسطات (أعلى من EMA20 و EMA50)" if close_price >= ema20 and close_price >= ema50 else "هابط أو ضغط بيعي"
    else:
        trend_description = "صعودي (أعلى من EMA20)" if close_price >= ema20 else "هابط (أسفل EMA20)"

    stop_loss_calculated = round(support_level - (1.2 * atr), 2)
    if stop_loss_calculated >= close_price:
        stop_loss_calculated = round(close_price - (1.5 * atr), 2)

    risk = close_price - stop_loss_calculated
    take_profit_calculated = round(close_price + (2.0 * risk), 2)
    
    risk_reward_valid = True
    if resistance_level > close_price and resistance_level < take_profit_calculated:
        potential_reward = resistance_level - close_price
        if risk > 0 and (potential_reward / risk) < 1.5:
            risk_reward_valid = False
        take_profit_calculated = resistance_level

    return {
        "close": close_price,
        "rsi": rsi,
        "rsi_description": rsi_description,
        "ema20": ema20,
        "ema50_str": ema50_str,
        "atr": atr,
        "trend_description": trend_description,
        "volume": current_volume,
        "avg_volume": avg_volume,
        "support": support_level,
        "resistance": resistance_level,
        "pattern": pattern,
        "stop_loss": stop_loss_calculated,
        "take_profit": take_profit_calculated,
        "risk_reward_valid": risk_reward_valid
    }

def ask_ai_decision(symbol, metrics, market_trend):
    prompt = f"""
أنت محلل مالي. البيانات التالية جرى حسابها ببرمجية بايثون:
- اتجاه السوق العام (SPY): {market_trend}
- السهم: {symbol}
- السعر الحالي: ${metrics['close']}
- مؤشر ATR: {metrics['atr']}
- حالة RSI: {metrics['rsi_description']}
- الاتجاه العام: {metrics['trend_description']} (EMA20: ${metrics['ema20']}, EMA50: {metrics['ema50_str']})
- حجم التداول: {metrics['volume']:,} (المتوسط لـ20 يوم: {metrics['avg_volume']:,})
- مستوى الدعم: ${metrics['support']} | المقاومة: ${metrics['resistance']}
- نموذج الشموع اليابانية: {metrics['pattern']}
- جدوى نسبة المخاطرة للعائد (R:R >= 1.5): {metrics['risk_reward_valid']}
- وقف الخسارة الديناميكي المحسوب بـ ATR: ${metrics['stop_loss']}
- هدف جني الأرباح المحسوب: ${metrics['take_profit']}

قواعد التحليل:
1. القرار يكون BUY فقط إذا كان اتجاه السوق أو السهم صعودياً، والسعر قريباً من الدعم، وتظهر شمعة إيجابية أو انعكاسية، وكانت جدوى المخاطرة للعائد مقبولة (True).
2. إذا كانت جدوى المخاطرة للعائد غير مقبولة (False)، أو كان السعر في اتجاه هابط صريح أسفل EMA50 والشمعة غير انعكاسية، اجعل القرار HOLD.
3. استخدم كلمة 'صعودي' لوصف الاتجاه الصاعد.

أرجع الإجابة بصيغة JSON فقط:
{{
  "action": "BUY" or "HOLD",
  "reason": "تفسير دقيق يربط اتجاه السوق والسهم ونموذج الشمعة وحجم التداول ونسبة المخاطرة للعائد"
}}
"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    try:
        res_obj = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response = res_obj.json()
        if "choices" in response:
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            return {"action": "HOLD", "reason": "خطأ في الاستجابة من OpenAI"}
    except Exception as e:
        return {"action": "HOLD", "reason": "خطأ في المعالجة"}

def run_hybrid_bot(symbol, market_trend):
    metrics = get_stock_metrics(symbol)
    if not metrics:
        print(f"فشل جلب البيانات للسهم {symbol}")
        return

    ai_decision = ask_ai_decision(symbol, metrics, market_trend)
    is_buy = ai_decision.get("action") == "BUY"
    action_ar = "شراء (BUY)" if is_buy else "انتظار (HOLD)"
    vol_status = "مرتفع 📈" if metrics['volume'] > metrics['avg_volume'] else "طبيعي أو منخفض 📉"

    status_note = "" if is_buy else " (افتراضي عند التفعيل)"

    msg = (
        f"🤖 <b>تنبيه التحليل الفني المطور</b>\n\n"
        f"🌐 <b>اتجاه السوق (SPY):</b> {market_trend}\n"
        f"📈 <b>السهم:</b> {symbol}\n"
        f"💵 <b>السعر الحالي:</b> ${metrics['close']}\n"
        f"🕯️ <b>نموذج الشمعة:</b> {metrics['pattern']}\n"
        f"📏 <b>مؤشر ATR:</b> {metrics['atr']}\n"
        f"📊 <b>RSI:</b> {metrics['rsi_description']}\n"
        f"📉 <b>الاتجاه:</b> {metrics['trend_description']}\n"
        f"🛡️ <b>الدعم:</b> ${metrics['support']} | 🧗 <b>المقاومة:</b> ${metrics['resistance']}\n"
        f"📦 <b>الحجم:</b> {metrics['volume']:,} ({vol_status})\n"
        f"🎯 <b>الهدف المقترح:</b> ${metrics['take_profit']}{status_note} | 🛑 <b>الوقف (ATR):</b> ${metrics['stop_loss']}{status_note}\n\n"
        f"🎯 <b>القرار:</b> <code>{action_ar}</code>\n"
        f"💡 <b>السبب الفني:</b> {ai_decision.get('reason')}"
    )
    send_telegram_msg(msg)

    if is_buy:
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            take_profit=TakeProfitRequest(limit_price=metrics['take_profit']),
            stop_loss=StopLossRequest(stop_price=metrics['stop_loss'])
        )
        order = trading_client.submit_order(order_data=order_data)
        send_telegram_msg(f"✅ <b>تم تنفيذ أمر الشراء للسهم {symbol}</b>\n🎯 الهدف: ${metrics['take_profit']} | 🛑 الوقف: ${metrics['stop_loss']}")

market_trend = get_market_trend()
symbols = ["AMIX", "ADXN"]
for symbol in symbols:
    run_hybrid_bot(symbol, market_trend)
    time.sleep(12)
