import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "my_secret_key_123").strip()

def send_telegram_msg(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram Error:", e)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No payload"}), 400
    
    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"status": "unauthorized"}), 401
    
    symbol = data.get("symbol", "غير محدد")
    price = data.get("price", "0.0")
    action = data.get("action", "INFO")
    reason = data.get("reason", "تنبيه منفذ من TradingView")
    
    msg = (
        f"⚡ <b>تنبيه لحظي من TradingView</b>\n\n"
        f"📈 <b>السهم:</b> {symbol}\n"
        f"💵 <b>السعر اللحظي:</b> ${price}\n"
        f"🎯 <b>نوع التنبيه:</b> <code>{action}</code>\n"
        f"💡 <b>السبب:</b> {reason}"
    )
    send_telegram_msg(msg)
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
