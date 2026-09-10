import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from alpaca.trading.client import TradingClient

load_dotenv(override=True)

app = Flask(__name__)

# المتغيرات الأساسية للمشروع
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

# تهيئة عميل Alpaca (ورقي)
trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

# بيانات الأسهم المملوكة يدويًا
MANUAL_POSITIONS = {
    "AMIX": {"qty": 427, "avg_price": 13.86},
    "ADXN": {"qty": 863, "avg_price": 8.85}
}

# ذاكرة منع التكرار
LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400  # 4 ساعات

def send_telegram_msg(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Warning: BOT_TOKEN or CHAT_ID missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Sent: Status {res.status_code}")
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_zoya_compliance(symbol):
    if not ZOYA_API_KEY:
        print("Zoya Warning: ZOYA_API_KEY is not set.")
        return None
    
    headers = {
        "Authorization": f"Bearer {ZOYA_API_KEY}",
        "Content-Type": "application/json"
    }
    query = """
    query GetCompliance($symbol: String!) {
      security(symbol: $symbol) {
        symbol
        name
        compliance {
          status
          isCompliant
          report {
            nonPermissibleRevenuePercentage
            debtToMarketCapPercentage
            interestBearingAssetsPercentage
          }
        }
      }
    }
    """
    payload = {"query": query, "variables": {"symbol": symbol.upper()}}
    try:
        res = requests.post(ZOYA_GRAPHQL_URL, json=payload, headers=headers, timeout=10)
        print(f"Zoya Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            if "errors" in data:
                print(f"Zoya GraphQL Error: {data['errors']}")
                return None
            return data.get("data", {}).get("security", {}).get("compliance", {})
    except Exception as e:
        print(f"Error connecting to Zoya API: {e}")
    return None

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "message": "Trading Webhook Server is active"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json or {}
    print(f"Received Webhook Data: {data}")

    symbol = data.get("symbol", "").upper()
    price = data.get("price", "N/A")
    action = data.get("action", "ALERT")
    reason = data.get("reason", "تنبيه تلقائي")
    rsi = data.get("rsi")

    if not symbol:
        return jsonify({"status": "error", "message": "Symbol missing"}), 200

    # 1. منع التكرار خلال 4 ساعات
    current_time = time.time()
    if symbol in LAST_ALERT_TIME:
        elapsed = current_time - LAST_ALERT_TIME[symbol]
        if elapsed < ALERT_COOLDOWN_SECONDS:
            print(f"Ignored {symbol}: Cooldown active ({int(elapsed)}s remaining)")
            return jsonify({"status": "ignored", "reason": "Cooldown active"}), 200

    # 2. الفحص الشرعي عبر Zoya API
    zoya_data = get_zoya_compliance(symbol)
    
    if zoya_data:
        status = zoya_data.get("status", "UNKNOWN")
        report = zoya_data.get("report", {}) or {}
        debt = report.get("debtToMarketCapPercentage", 0) or 0
        rev = report.get("nonPermissibleRevenuePercentage", 0) or 0
        
        shariah_info = f"""
---
🕌 **تقرير الفحص الشرعي (Zoya API):**
✅ **الحالة:** `{status}`
📊 **نسبة الديون:** `{debt:.2f}%`
💰 **الإيرادات غير الحرّة:** `{rev:.2f}%`"""
    else:
        shariah_info = """
---
⚠️ **ملاحظة شرعية:** تعذر جلب البيانات التلقائية من Zoya (يرجى التحقق اليدوي)."""

    # 3. صياغة وإرسال التنبيه
    msg = f"""🔥 **تنبيه فرصة تداول**

🏷️ **السهم:** `{symbol}`
💵 **السعر:** `${price}`
🎯 **الإجراء:** `{action}`
📌 **السبب:** {reason}
{shariah_info}"""

    send_telegram_msg(msg)
    LAST_ALERT_TIME[symbol] = current_time

    return jsonify({"status": "success", "message": "Alert processed and sent to Telegram"}), 200

@app.route('/check-compliance', methods=['GET', 'POST'])
def run_compliance_check():
    """فحص أسهم المحفظة اليدوية"""
    if not MANUAL_POSITIONS:
        return jsonify({"status": "success", "message": "المحفظة فارغة"}), 200

    alerts = []
    for symbol in MANUAL_POSITIONS.keys():
        zoya_data = get_zoya_compliance(symbol)
        if zoya_data and not zoya_data.get("isCompliant", True):
            alerts.append(symbol)
            msg = f"⚠️ **تحذير شرعي:** سهم مملوك `{symbol}` تغيرت حالته إلى غير متوافق!"
            send_telegram_msg(msg)

    return jsonify({"status": "completed", "flagged_stocks": alerts}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
