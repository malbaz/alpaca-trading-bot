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
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"
    res = requests.get(url).json()
    if not res.get("results"):
        return None
    close_price = res["results"][0]["c"]
    
    url_hist = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/2026-01-01/2026-12-31?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}"
    res_hist = requests.get(url_hist).json()
    
    if res_hist.get("results"):
        closes = [item["c"] for item in reversed(res_hist["results"])]
        rsi = calculate_rsi(closes)
        ema20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)
    else:
        rsi = 50.0
        ema20 = close_price
        
    return {"close": close_price, "rsi": rsi, "ema20": ema20}

def ask_ai_decision(symbol, metrics):
    prompt = f"""
Analyze stock {symbol}:
Price: ${metrics['close']}
RSI: {metrics['rsi']}
EMA20: ${metrics['ema20']}

Respond ONLY with a JSON object. Write the 'reason' value in clear Arabic:
{{
  "action": "BUY" or "HOLD",
  "reason": "سبب القرار باللغة العربية المباشرة والواضحة",
  "stop_loss_pct": 0.01,
  "take_profit_pct": 0.02
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
            print("OpenAI Error Details:", response)
            return {"action": "HOLD", "reason": "خطأ في الاتصال بالذكاء الاصطناعي"}
    except Exception as e:
        print("AI Processing Error:", e)
        return {"action": "HOLD", "reason": "خطأ في المعالجة"}

def run_hybrid_bot(symbol):
    metrics = get_stock_metrics(symbol)
    if not metrics:
        print("فشل في جلب البيانات.")
        return

    ai_decision = ask_ai_decision(symbol, metrics)

    action_ar = "شراء" if ai_decision.get("action") == "BUY" else "الانتظار (HOLD)"

    msg = (
        f"🤖 *تنبيه بوت التداول*\n\n"
        f"📈 *السهم:* {symbol}\n"
        f"💵 *السعر الحالي:* ${metrics['close']}\n"
        f"📊 *مؤشر RSI:* {metrics['rsi']} | *المتوسط المتحرك EMA20:* ${metrics['ema20']}\n\n"
        f"🎯 *القرار:* `{action_ar}`\n"
        f"💡 *السبب:* {ai_decision.get('reason')}"
    )
    send_telegram_msg(msg)

    if ai_decision.get("action") == "BUY":
        close_price = metrics["close"]
        sl_pct = ai_decision.get("stop_loss_pct", 0.01)
        tp_pct = ai_decision.get("take_profit_pct", 0.02)
        
        stop_loss = round(close_price * (1 - sl_pct), 2)
        take_profit = round(close_price * (1 + tp_pct), 2)

        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        order = trading_client.submit_order(order_data=order_data)
        send_telegram_msg(f"✅ *تم تنفيذ أمر الشراء للسهم {symbol}* | رقم الأمر: `{order.id}`")
    else:
        print("القرار: انتظار. لم يتم تقديم أي أمر شراء.")

run_hybrid_bot("AAPL")
