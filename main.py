import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv(override=True)

app = Flask(__name__)

# المتغيرات الأساسية
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400

def send_telegram_msg(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_zoya_compliance(symbol):
    if not ZOYA_API_KEY:
        print("Zoya Warning: ZOYA_API_KEY is not configured in environment variables.")
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
        print(f"Zoya Response Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            if "errors" in data:
                print(f"Zoya GraphQL Errors: {data['errors']}")
                return None
            return data.get("data", {}).get("security", {}).get("compliance", {})
    except Exception as e:
        print(f"Zoya Connection Exception: {e}")
    return None

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "message": "Webhook Server is running"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    # استقبال أي بيانات دون أي شروط مصادقة لمنع 401 نهائياً
    data = request.json or {}
    print(f"Received webhook payload: {data}")

    symbol = data.get("symbol", "").upper()
    price = data.get("price", "N/A")
    action = data.get("action", "ALERT")
    reason = data.get("reason", "تنبيه تلقائي")
    rsi = data.get("rsi")

    if not symbol:
        return jsonify({"status": "error", "message": "Symbol missing"}), 200

    # آلية Cooldown
    current_time = time.time()
    if symbol in LAST_ALERT_TIME:
        if current_time - LAST_ALERT_TIME[symbol] < ALERT_COOLDOWN_SECONDS:
            return jsonify({"status": "ignored", "reason": "Rate limited"}), 200

    # فحص Zoya
    zoya_data = get_zoya_compliance(symbol)
    if zoya_data and zoya_data.get("isCompliant") and zoya_data.get("status") == "COMPLIANT":
        report = zoya_data.get("report", {})
        debt = report.get("debtToMarketCapPercentage", 0) or 0
        rev = report.get("nonPermissibleRevenuePercentage", 0) or 0
        
        msg = f"""🔥 **فرصة شرعية جديدة**

🏷️ **السهم:** `{symbol}`
💵 **السعر:** `${price}`
🎯 **النوع:** `{action}`
📌 **السبب:** {reason}

---
🕌 **تقرير Zoya الشرعي:**
✅ **الحالة:** متوافق شرعياً
📊 **الديون:** `{debt:.2f}%`
💰 **الإيرادات غير الحرّة:** `{rev:.2f}%`"""

        send_telegram_msg(msg)
        LAST_ALERT_TIME[symbol] = current_time
        return jsonify({"status": "success", "message": "Alert sent to Telegram"}), 200

    return jsonify({"status": "ignored", "reason": "Non-compliant or unverified"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
