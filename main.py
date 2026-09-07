import os
import requests
import json
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

def get_stock_metrics(symbol):
    url_hist = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/2026-01-01/2026-12-31?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}"
    res_hist = requests.get(url_hist).json()
    
    results = res_hist.get("results", [])
    if not results or len(results) < 5:
        return None

    closes = [item["c"] for item in reversed(results)]
    volumes = [item["v"] for item in reversed(results)]
    lows = [item["l"] for item in reversed(results)]
    highs = [item["h"] for item in reversed(results)]

    close_price = closes[-1]
    rsi = calculate_rsi(closes)
    ema20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)
    
    current_volume = int(round(volumes[-1]))
    avg_volume = int(round(sum(volumes[-20:]) / min(len(volumes), 20)))
    
    support_level = min(lows[-20:])
    resistance_level = max(highs[-20:])

    if rsi < 30:
        rsi_description = f"{rsi} (منطقة ذروة بيع صريحة Oversold لأن القيمة أدنى من 30)"
    elif rsi > 70:
        rsi_description = f"{rsi} (منطقة ذروة شراء صريحة Overbought لأن القيمة أعلى من 70)"
    else:
        rsi_description = f"{rsi} (منطقة محايدة بين 30 و70)"

    trend_description = "اتجاه صعودي (السعر أعلى من EMA20)" if close_price >= ema20 else "اتجاه هابط (السعر أسفل EMA20)"

    stop_loss_calculated = round(support_level * 0.98, 2)
    if stop_loss_calculated >= close_price:
        stop_loss_calculated = round(close_price * 0.95, 2)

    risk = close_price - stop_loss_calculated
    take_profit_calculated = round(close_price + (risk * 2), 2)

    return {
        "close": close_price,
        "rsi": rsi,
        "rsi_description": rsi_description,
        "ema20": ema20,
        "trend_description": trend_description,
        "volume": current_volume,
        "avg_volume": avg_volume,
        "support": support_level,
        "resistance": resistance_level,
        "stop_loss": stop_loss_calculated,
        "take_profit": take_profit_calculated
    }

def ask_ai_decision(symbol, metrics):
    prompt = f"""
أنت محلل مالي محترف. المعطيات التالية جرى تقييمها وتدقيقها حسابياً ببرمجية بايثون وفق معايير TradingView وInvestopedia:
- السهم: {symbol}
- السعر الحالي: ${metrics['close']}
- حالة RSI: {metrics['rsi_description']}
- الاتجاه العام: {metrics['trend_description']} (المتوسط EMA20: ${metrics['ema20']})
- حجم التداول: {metrics['volume']:,} (المتوسط لـ20 يوم: {metrics['avg_volume']:,})
- مستوى الدعم (أدنى 20 يوم): ${metrics['support']}
- مستوى المقاومة (أعلى 20 يوم): ${metrics['resistance']}
- مستوى وقف الخسارة (أسفل الدعم بنسبة 2%): ${metrics['stop_loss']}
- هدف جني الأرباح (نسبة المخاطرة للعائد 1:2): ${metrics['take_profit']}

قواعد الصياغة والتحليل:
1. اعتمد التقييم المحسوب لحالة RSI والاتجاه العام كما هو دون أي تعديل.
2. استخدم كلمة 'صعودي' لوصف الاتجاه الصاعد وتجنب الأخطاء الإملائية.
3. القرار يكون BUY فقط إذا كان السعر قريباً من الدعم مع وجود حجم تداول مرتفع وتأكيد ارتداد، وغير ذلك يكون القرار HOLD.

أرجع الإجابة بصيغة JSON فقط:
{{
  "action": "BUY" or "HOLD",
  "reason": "تفسير دقيق باللغة العربية المباشرة يربط السعر بالحجم ومستوى الدعم والاتجاه"
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
    vol_status = "مرتفع 📈" if metrics['volume'] > metrics['avg_volume'] else "منخفض/طبيعي 📉"

    msg = (
        f"🤖 *تنبيه التحليل الفني المطور*\n\n"
        f"📈 *السهم:* {symbol}\n"
        f"💵 *السعر الحالي:* ${metrics['close']}\n"
        f"📊 *RSI:* {metrics['rsi_description']}\n"
        f"📈 *الاتجاه:* {metrics['trend_description']}\n"
        f"🛡️ *الدعم:* ${metrics['support']} | 🧗 *المقاومة:* ${metrics['resistance']}\n"
        f"📦 *الحجم:* {metrics['volume']:,} (الحالة: {vol_status})\n"
        f"🎯 *الهدف (1:2):* ${metrics['take_profit']} | 🛑 *الوقف (أسفل الدعم):* ${metrics['stop_loss']}\n\n"
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
