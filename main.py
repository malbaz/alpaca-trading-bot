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
        "text": message_text,
        "parse_mode": "HTML"
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
        raw_data = request.get_data(as_text=True)
        data = {}

        try:
            data = json.loads(raw_data)
        except Exception:
            data = request.get_json(force=True, silent=True) or {}

        raw_symbol = str(data.get("symbol", "") or data.get("ticker", "") or "").strip().upper()
        
        if ":" in raw_symbol:
            symbol = raw_symbol.split(":")[-1]
        else:
            symbol = raw_symbol

        price = str(data.get("price", "N/A")).strip()
        action = str(data.get("action", "ALERT")).strip().upper()
        reason = str(data.get("reason", "تنبيه تلقائي")).strip()
        interval = str(data.get("interval", "غير محدد")).strip()
        volume = str(data.get("volume", "N/A")).strip()

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
                        shariah_text = f"✅ <b>متوافق</b> ({status})\n   • الديون: {debt:.2f}%\n   • غير المباح: {rev:.2f}%"
                    else:
                        shariah_text = f"❌ <b>غير متوافق</b> ({status})\n   • الديون: {debt:.2f}%\n   • غير المباح: {rev:.2f}%"
            except Exception:
                pass

        action_emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "🔵"

        message_text = (
            f"<b>{action_emoji} تنبيه فرصة تداول: {symbol}</b>\n\n"
            f"📌 <b>السهم:</b> <code>{symbol}</code>\n"
            f"💰 <b>السعر الحالي:</b> ${price}\n"
            f"⚡ <b>نوع الإشارة:</b> {action}\n"
            f"⏱️ <b>الفريم الزمني:</b> {interval}\n"
            f"📊 <b>حجم التداول:</b> {volume}\n"
            f"📝 <b>السبب:</b> {reason}\n\n"
            f"⚖️ <b>الوضع الشرعي (Zoya):</b>\n{shariah_text}"
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
