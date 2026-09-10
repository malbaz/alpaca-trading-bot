import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

# تحميل البيئة بدون تجاوز متغيرات Render
load_dotenv(override=False)

app = Flask(__name__)

ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

WATCHLIST_SYMBOLS = [
    "AAPL", "NVDA", "AMIX", "ADXN", "INDP", "AAL", 
    "VALE", "BIAF", "BITF", "CLNE", "SKYE", "NAUT", "SGLY", "JOBY"
]

LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400

def send_telegram_msg(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    
    # طباعة جزء من التوكن للتأكد من قيمته الحقيقية في السجلات
    masked_token = token[:8] + "..." if token else "None"
    print(f"DEBUG: Executing with Token prefix: '{masked_token}', Chat ID: '{chat_id}'")
    
    if not token or not chat_id:
        print("Telegram Config Error: TOKEN or CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Response Status: {res.status_code}")
        print(f"Telegram Response Body: {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"Telegram Exception: {e}")
        return False

def get_zoya_compliance(symbol):
    if not ZOYA_API_KEY:
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
          }
        }
      }
    }
    """
    payload = {"query": query, "variables": {"symbol": symbol.upper()}}
    try:
        res = requests.post(ZOYA_GRAPHQL_URL, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "errors" not in data:
                return data.get("data", {}).get("security", {}).get("compliance", {})
    except Exception as e:
        print(f"Zoya Error ({symbol}): {e}")
    return None

def scheduled_market_scan():
    print("Running scheduled market scan...")
    valid_opportunities = []

    for symbol in WATCHLIST_SYMBOLS:
        zoya_data = get_zoya_compliance(symbol)
        if zoya_data and zoya_data.get("isCompliant") and zoya_data.get("status") == "COMPLIANT":
            valid_opportunities.append(f"🟢 `{symbol}`: متوافق شرعياً | إشارة: **فرصة دخول**")

    if valid_opportunities:
        report_msg = f"📊 **تقرير الفحص المباشر الموحد**\n\n" + "\n".join(valid_opportunities)
        send_telegram_msg(report_msg)

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json or {}
    symbol = data.get("symbol", "").upper()
    price = data.get("price", "N/A")
    action = data.get("action", "ALERT")
    reason = data.get("reason", "تنبيه تلقائي")

    if not symbol:
        return jsonify({"status": "error", "message": "Symbol missing"}), 400

    current_time = time.time()
    if symbol in LAST_ALERT_TIME:
        if current_time - LAST_ALERT_TIME[symbol] < ALERT_COOLDOWN_SECONDS:
            return jsonify({"status": "ignored", "reason": "Cooldown active"}), 200

    zoya_data = get_zoya_compliance(symbol)
    
    if zoya_data:
        status = zoya_data.get("status", "UNKNOWN")
        report = zoya_data.get("report", {}) or {}
        debt = report.get("debtToMarketCapPercentage", 0) or 0
        rev = report.get("nonPermissibleRevenuePercentage", 0) or 0
        
        shariah_info = f"""---
🕌 **تقرير الفحص الشرعي (Zoya API):**
✅ **الحالة:** `{status}`
📊 **نسبة الديون:** `{debt:.2f}%`
💰 **الإيرادات غير الحرّة:** `{rev:.2f}%`"""
    else:
        shariah_info = """---
⚠️ **ملاحظة شرعية:** تعذر جلب البيانات التلقائية من Zoya (يرجى التحقق اليدوي)."""

    msg = f"""🔥 **تنبيه فرصة تداول**

🏷️ **السهم:** `{symbol}`
💵 **السعر:** `${price}`
🎯 **الإجراء:** `{action}`
📌 **السبب:** {reason}
{shariah_info}"""

    sent = send_telegram_msg(msg)
    if sent:
        LAST_ALERT_TIME[symbol] = current_time
        return jsonify({"status": "success", "message": "Alert sent successfully"}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to send Telegram message"}), 500

scheduler = BackgroundScheduler()
scheduler.add_job(func=scheduled_market_scan, trigger="interval", hours=1)
if not scheduler.running:
    scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
