import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv(override=False)

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400

def send_discord_msg(message_text):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("CRITICAL: DISCORD_WEBHOOK_URL is empty or not set!")
        return False

    payload = {"content": message_text}
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        print(f"Discord Response Code: {res.status_code}")
        print(f"Discord Response Body: {res.text}")
        return res.status_code in [200, 204]
    except Exception as e:
        print(f"Discord Request Exception: {e}")
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
    payload = {"query": query, "variables": {"symbol": str(symbol).upper()}}
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
        data = request.get_json(force=True, silent=True) or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        price = str(data.get("price", "N/A")).strip()
        action = str(data.get("action", "ALERT")).strip()
        reason = str(data.get("reason", "تنبيه تلقائي")).strip()

        if not symbol:
            return jsonify({"status": "error", "message": "Symbol missing"}), 400

        current_time = time.time()
        if symbol in LAST_ALERT_TIME:
            if current_time - LAST_ALERT_TIME[symbol] < ALERT_COOLDOWN_SECONDS:
                return jsonify({"status": "ignored", "reason": "Cooldown active"}), 200

        shariah_text = "ℹ️ فحص الشرعية غير متاح"

        if ZOYA_API_KEY:
            try:
                zoya_data = get_zoya_compliance(symbol)
                if zoya_data:
                    status = str(zoya_data.get("status", "UNKNOWN"))
                    report = zoya_data.get("report") or {}
                    debt = float(report.get("debtToMarketCapPercentage") or 0.0)
                    rev = float(report.get("nonPermissibleRevenuePercentage") or 0.0)
                    
                    if zoya_data.get("isCompliant"):
                        shariah_text = f"✅ **متوافق:** `{status}` | 📊 **الديون:** `{debt:.2f}%` | 💰 **غير المباح:** `{rev:.2f}%`"
                    else:
                        shariah_text = f"❌ **غير متوافق:** `{status}` | 📊 **الديون:** `{debt:.2f}%` | 💰 **غير المباح:** `{rev:.2f}%`"
            except Exception as z_err:
                print(f"Zoya Bypass: {z_err}")

        message_text = (
            f"🔥 **تنبيه فرصة تداول: {symbol}**\n"
            f"• **السهم:** `{symbol}`\n"
            f"• **السعر:** `${price}`\n"
            f"• **الإجراء:** `{action}`\n"
            f"• **السبب:** {reason}\n"
            f"• **الفحص الشرعي:** {shariah_text}"
        )

        sent = send_discord_msg(message_text)
        if sent:
            LAST_ALERT_TIME[symbol] = current_time
            return jsonify({"status": "success", "message": "Alert sent to Discord"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send to Discord"}), 500

    except Exception as err:
        print(f"Server Error: {err}")
        return jsonify({"status": "error", "message": str(err)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
