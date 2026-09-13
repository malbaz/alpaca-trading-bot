import os
import json
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv(override=False)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

def send_telegram_msg(message_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception:
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
    except Exception:
        pass
    return None

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # قراءة البيانات بأي شكل يرسله TradingView
        raw_data = request.get_data(as_text=True)
        data = {}

        try:
            data = json.loads(raw_data)
        except Exception:
            data = request.get_json(force=True, silent=True) or {}

        # استخراج اسم السهم
        raw_symbol = str(data.get("symbol", "") or data.get("ticker", "") or "").strip().upper()
        
        if ":" in raw_symbol:
            symbol = raw_symbol.split(":")[-1]
        else:
            symbol = raw_symbol

        price = str(data.get("price", "N/A")).strip()
        action = str(data.get("action", "ALERT")).strip()
        reason = str(data.get("reason", "تنبيه تلقائي")).strip()

        # إذا لم يتم استخراج سهم محدد، استخرج النص كاملاً
        if not symbol:
            symbol = "تنبيه عام"
            reason = raw_data if raw_data else "تنبيه بدون بيانات"

        shariah_text = "فحص الشرعية غير متاح"

        if symbol != "تنبيه عام":
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
            except Exception:
                pass

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
            return jsonify({"status": "success", "message": "Alert sent to Telegram"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send to Telegram"}), 500

    except Exception as err:
        return jsonify({"status": "error", "message": str(err)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
