import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv(override=True)

app = Flask(__name__)

# المتغيرات الأساسية للمشروع
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

# قائمة الأسهم المتابعة للفحص الدوري
WATCHLIST_SYMBOLS = [
    "AAPL", "NVDA", "AMIX", "ADXN", "INDP", "AAL", 
    "VALE", "BIAF", "BITF", "CLNE", "SKYE", "NAUT", "SGLY", "JOBY"
]

# ذاكرة منع تكرار التنبيهات (4 ساعات)
LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400

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
    """مجدول الفحص الدوري المدمج لإرسال تقارير الأسهم الشرعية القوية فقط"""
    print("Running scheduled market scan...")
    valid_opportunities = []

    for symbol in WATCHLIST_SYMBOLS:
        zoya_data = get_zoya_compliance(symbol)
        
        # تصفية الشرعية: نأخذ فقط الأسهم المعتمدة
        if zoya_data and zoya_data.get("isCompliant") and zoya_data.get("status") == "COMPLIANT":
            valid_opportunities.append(f"🟢 `{symbol}`: متوافق شرعياً | إشارة: **فرصة دخول**")

    if valid_opportunities:
        report_msg = f"📊 **تقرير الفحص المباشر الموحد**\n"
        report_msg += f"تم فحص الأسهم ومطابقتها للشريعة:\n\n"
        report_msg += "\n".join(valid_opportunities)
        send_telegram_msg(report_msg)

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "message": "Unified Trading Webhook Server is active"}), 200

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

    # 1. منع التكرار
    current_time = time.time()
    if symbol in LAST_ALERT_TIME:
        if current_time - LAST_ALERT_TIME[symbol] < ALERT_COOLDOWN_SECONDS:
            return jsonify({"status": "ignored", "reason": "Cooldown active"}), 200

    # 2. الفحص الشرعي عبر Zoya
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

    # 3. إرسال التنبيه الفوري
    msg = f"""🔥 **تنبيه فرصة تداول**

🏷️ **السهم:** `{symbol}`
💵 **السعر:** `${price}`
🎯 **الإجراء:** `{action}`
📌 **السبب:** {reason}
{shariah_info}"""

    send_telegram_msg(msg)
    LAST_ALERT_TIME[symbol] = current_time

    return jsonify({"status": "success", "message": "Alert processed and sent to Telegram"}), 200

# بدء تشغيل المجدول تلقائياً مع التطبيق
scheduler = BackgroundScheduler()
scheduler.add_job(func=scheduled_market_scan, trigger="interval", hours=1)
if not scheduler.running:
    scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
