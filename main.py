import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

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
    
    masked_token = token[:8] + "..." if token else "None"
    print(f"DEBUG: Token prefix: '{masked_token}', Chat ID: '{chat_id}'")
    
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
        print(f"Telegram Status: {res.status_code}, Body: {res.text}")
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

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
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

        # فحص Zoya مع التجاوز الآمن في حال وجود خطأ
        shariah_info = ""
        try:
            zoya_data = get_zoya_compliance(symbol)
            if zoya_data:
                status = zoya_data.get("status", "UNKNOWN")
                report = zoya_data.get("report") or {}
                debt = report.get("debtToMarketCapPercentage") or 0.0
                rev = report.get("nonPermissibleRevenuePercentage") or 0.0
                
                shariah_info = f"\n---\n🕌 **تقرير الفحص الشرعي (Zoya):**\n✅ **الحالة:** `{status}`\n📊 **نسبة الديون:** `{debt:.2f}%`\n💰 **الإيرادات غير الحرّة:** `{rev:.2f}%`"
            else:
                shariah_info = "\n---\n⚠️ **ملاحظة شرعية:** تعذر جلب البيانات التلقائية من Zoya."
        except Exception as z_err:
            print(f"Safe Zoya Bypass Error: {z_err}")
            shariah_info = "\n---\n⚠️ **ملاحظة شرعية:** تعذر جلب البيانات التلقائية من Zoya."

        msg = f"🔥 **تنبيه فرصة تداول**\n\n🏷️ **السهم:** `{symbol}`\n💵 **السعر:** `${price}`\n🎯 **الإجراء:** `{action}`\n📌 **السبب:** {reason}{shariah_info}"

        sent = send_telegram_msg(msg)
        if sent:
            LAST_ALERT_TIME[symbol] = current_time
            return jsonify({"status": "success", "message": "Alert sent successfully"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send Telegram message"}), 500

    except Exception as main_err:
        print(f"Webhook Execution Error: {main_err}")
        return jsonify({"status": "error", "message": str(main_err)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
