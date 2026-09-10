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

def send_discord_msg(embed_data):
    if not DISCORD_WEBHOOK_URL:
        print("Discord Error: DISCORD_WEBHOOK_URL missing")
        return False

    payload = {
        "username": "BazTech Alerts",
        "embeds": [embed_data]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Discord Status: {res.status_code}")
        return res.status_code in [200, 204]
    except Exception as e:
        print(f"Discord Exception: {e}")
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

        # جلب بيانات Zoya
        shariah_text = "⚠️ تعذر جلب البيانات التلقائية من Zoya"
        color = 3447003  # الأزرق الافتراضي

        try:
            zoya_data = get_zoya_compliance(symbol)
            if zoya_data:
                status = zoya_data.get("status", "UNKNOWN")
                report = zoya_data.get("report") or {}
                debt = report.get("debtToMarketCapPercentage") or 0.0
                rev = report.get("nonPermissibleRevenuePercentage") or 0.0
                
                if zoya_data.get("isCompliant"):
                    color = 5763719  # أخضر
                    shariah_text = f"✅ **الحالة:** `{status}`\n📊 **الديون:** `{debt:.2f}%`\n💰 **غير الحرّة:** `{rev:.2f}%`"
                else:
                    color = 15548997  # أحمر
                    shariah_text = f"❌ **الحالة:** `{status}`\n📊 **الديون:** `{debt:.2f}%`\n💰 **غير الحرّة:** `{rev:.2f}%`"
        except Exception as z_err:
            print(f"Zoya Bypass: {z_err}")

        embed_data = {
            "title": f"🔥 تنبيه فرصة تداول: {symbol}",
            "color": color,
            "fields": [
                {"name": "السهم", "value": f"`{symbol}`", "inline": True},
                {"name": "السعر", "value": f"`${price}`", "inline": True},
                {"name": "الإجراء", "value": f"`{action}`", "inline": True},
                {"name": "السبب", "value": str(reason), "inline": False},
                {"name": "🕌 الفحص الشرعي (Zoya)", "value": shariah_text, "inline": False}
            ]
        }

        sent = send_discord_msg(embed_data)
        if sent:
            LAST_ALERT_TIME[symbol] = current_time
            return jsonify({"status": "success", "message": "Alert sent to Discord"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send to Discord"}), 500

    except Exception as err:
        print(f"Webhook Execution Error: {err}")
        return jsonify({"status": "error", "message": str(err)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
