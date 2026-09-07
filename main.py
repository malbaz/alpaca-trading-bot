import os
import json
import requests
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram Error:", e)

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

def get_stock_metrics(symbol):
    url_hist = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/2026-01-01/2026-12-31?adjusted=true&sort=desc&limit=60&apiKey={POLYGON_API_KEY}"
    res_hist = requests.get(url_hist).json()
    
    results = res_hist.get("results", [])
    if not results or len(results) < 20:
        return None

    results_sorted = list(reversed(results))
    closes = [item["c"] for item in results_sorted]
    volumes = [item["v"] for item in results_sorted]
    lows = [item["l"] for item in results_sorted]
    highs = [item["h"] for item in results_sorted]

    close_price = closes[-1]
    rsi = calculate_rsi(closes)
    ema20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)
    ema50 = round(sum(closes[-50:]) / min(len(closes), 50), 2) if len(closes) >= 50 else ema20
    
    atr = calculate_atr(highs, lows, closes)
    current_volume = int(round(volumes[-1]))
    avg_volume = int(round(sum(volumes[-20:]) / min(len(volumes), 20)))
    
    support_level = min(lows[-20:])
    resistance_level = max(highs[-20:])

    is_bullish_candle = closes[-1] > closes[-2]

    if rsi < 30:
        rsi_description = f"{rsi} (منطقة ذروة بيع صريحة أدنى من 30)"
    elif rsi > 70:
        rsi_description = f"{rsi} (منطقة ذروة شراء صريحة أعلى من 70)"
    else:
        rsi_description = f"{rsi} (منطقة محايدة)"

    trend_description = "صعودي على المتوسطات (أعلى من EMA20 و EMA50)" if close_price >= ema20 and close_price >= ema50 else "هابط أو غير مستقر"

    stop_loss_calculated = round(support_level - (1.2 * atr), 2)
    if stop_loss_calculated >= close_price:
        stop_loss_calculated = round(close_price - (1.5 * atr), 2)

    risk = close_price - stop_loss_calculated
    take_profit_calculated = round(close_price + (2.0 * risk), 2)

    return {
        "close": close_price,
        "rsi": rsi,
        "rsi_description": rsi_description,
        "ema20": ema20,
        "ema50": ema50,
        "atr": atr,
        "trend_description": trend_description,
        "volume": current_volume,
        "avg_volume": avg_volume,
        "support": support_level,
        "resistance": resistance_level,
        "is_bullish_candle": is_bullish_candle,
        "stop_loss": stop_loss_calculated,
        "take_profit": take_profit_calculated
    }

def ask_ai_decision(symbol, metrics):
    prompt = f"""
أنت محلل مالي. البيانات التالية جرى حسابها ببرمجية بايثون:
- السهم: {symbol}
- السعر الحالي: ${metrics['close']}
- مؤشر ATR: {metrics['atr']}
- حالة RSI: {metrics['rsi_description']}
- الاتجاه العام: {metrics['trend_description']} (EMA20: ${metrics['ema20']}, EMA50: ${metrics['ema50']})
- حجم التداول: {metrics['volume']:,} (المتوسط لـ20 يوم: {metrics['avg_volume']:,})
- مستوى الدعم: ${metrics['support']} | المقاومة: ${metrics['resistance']}
- شمعة صاعدة إيجابية: {metrics['is_bullish_candle']}
- وقف الخسارة المحسوب بـ ATR أسفل الدعم: ${metrics['stop_loss']}
- الهدف المحسوب (نسبة 1:2): ${metrics['take_profit']}

قواعد التحليل:
1. القرار يكون BUY فقط إذا كان السعر قريباً من الدعم، والشمعة الحالية إيجابية (True)، والاتجاه العام صعودي أو محايد قادم من ارتداد مع حجم تداول مناسب.
2. إذا كان السعر في اتجاه هابط صريح أسفل EMA50 والشمعة هابطة، اجعل القرار HOLD.
3. استخدم كلمة 'صعودي' لوصف الاتجاه الصاعد.

أرجع الإجابة بصيغة JSON فقط:
{{
  "action": "BUY" or "HOLD",
  "reason": "تفسير دقيق يربط السعر والاتجاه وحجم التداول ومؤشر ATR"
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

def run_hybrid_bot(symbol):
    metrics = get_stock_metrics(symbol)
    if not metrics:
        print(f"فشل جلب البيانات للسهم {symbol}")
        return

    ai_decision = ask_ai_decision(symbol, metrics)
    action_ar = "شراء (BUY)" if ai_decision.get("action") == "BUY" else "انتظار (HOLD)"
    vol_status = "مرتفع 📈" if metrics['volume'] > metrics['avg_volume'] else "طبيعي أو منخفض 📉"

    msg = (
        f"🤖 *تنبيه التحليل الفني المطور*\n\n"
        f"📈 *السهم:* {symbol}\n"
        f"💵 *السعر الحالي:* ${metrics['close']}\n"
        f"📏 *مؤشر ATR:* {metrics['atr']}\n"
        f"📊 *RSI:* {metrics['rsi_description']}\n"
        f"📉 *الاتجاه:* {metrics['trend_description']}\n"
        f"🛡️ *الدعم:* ${metrics['support']} | 🧗 *المقاومة:* ${metrics['resistance']}\n"
        f"📦 *الحجم:* {metrics['volume']:,} ({vol_status})\n"
        f"🎯 *الهدف المقترح:* ${metrics['take_profit']} | 🛑 *الوقف (ديناميكي ATR):* ${metrics['stop_loss']}\n\n"
        f"🎯 *القرار:* `{action_ar}`\n"
        f"💡 *السبب الفني:* {ai_decision.get('reason')}"
    )
    send_telegram_msg(msg)

    if ai_decision.get("action") == "BUY":
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            take_profit=TakeProfitRequest(limit_price=metrics['take_profit']),
            stop_loss=StopLossRequest(stop_price=metrics['stop_loss'])
        )
        order = trading_client.submit_order(order_data=order_data)
        send_telegram_msg(f"✅ *تم تنفيذ أمر الشراء للسهم {symbol}*\n🎯 الهدف: ${metrics['take_profit']} | 🛑 الوقف: ${metrics['stop_loss']}")

symbols = ["AMIX", "ADXN"]
for symbol in symbols:
    run_hybrid_bot(symbol)
