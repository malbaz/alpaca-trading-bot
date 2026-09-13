import os
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv(override=False)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400

def send_telegram_msg(message_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing!")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Response Status: {res.status_code}")
        if res.status_code != 200:
            print(f"Telegram Raw Body: {res.text}")
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
    payload = {"query": query, "variables": {"symbol": str(symbol).upper()}}
    try:
        res = requests.post(ZOYA_GRAPHQL_URL, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("data", {}).get("security", {}).get("compliance", {})
    except Exception as e:
        print(f"Zoya Exception: {e}")
    return None

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        # تنظيف اسم السهم واستخراجه في حال إرساله بصيغة NASDAQ:AMIX
        raw_symbol = str(data.get("symbol", "")).strip().upper()
        symbol = raw_symbol.split(":")[-1] if ":" in raw_symbol else raw_symbol

        price = str(data.get("price", "N/A")).strip()
        action = str(data.get("action", "ALERT")).strip()
        reason = str(data.get("reason", "تنبيه تلقائي")).strip()

        if not symbol:
            return jsonify({"status": "error", "message": "Symbol missing"}), 400

        current_time = time.time()
        if symbol in LAST_ALERT_TIME:
            if current_time - LAST_ALERT_TIME[symbol] < ALERT_COOLDOWN_SECONDS:
                return jsonify({"status": "ignored", "reason": "Cooldown active"}), 200

        shariah_text = "فحص الشرعية غير متاح"

        try:
            zoya_data = get_zoya_compliance(symbol)
            if zoya_data:
                status = str(zoya_data.get("status", "UNKNOWN"))
                report = zoya_data.get("report") or {}
                debt = float(report.get("debtToMarketCapPercentage") or 0.0)
                rev = float(report.get("nonPermissibleRevenuePercentage") or 0.0)
                
                if zoya_data.get("isCompliant"):
                    shariah_text = f"متوافق: {status} | الديون: {debt:.2f}% | غير المباح: {rev:.2f}%"
                else:
                    shariah_text = f"غير متوافق: {status} | الديون: {debt:.2f}% | غير المباح: {rev:.2f}%"
        except Exception as z_err:
            print(f"Zoya Processing Error: {z_err}")

        message_text = (
            f"تنبيه فرصة تداول: {symbol}\n"
            f"• السهم: {symbol}\n"
            f"• السعر: ${price}\n"
            f"• الإجراء: {action}\n"
            f"• السبب: {reason}\n"
            f"• الفحص الشرعي: {shariah_text}"
        )

        sent = send_telegram_msg(message_text)
        if sent:
            LAST_ALERT_TIME[symbol] = current_time
            return jsonify({"status": "success", "message": "Alert sent to Telegram"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send to Telegram"}), 500

    except Exception as err:
        print(f"Webhook Error: {err}")
        return jsonify({"status": "error", "message": str(err)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
