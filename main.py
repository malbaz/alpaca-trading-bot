# كود main.py المحدث بدون فحص شرعي ومع بطاقة التوصية الشاملة

import os
import json
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv(override=False)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

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
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

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

        name = str(data.get("name", symbol)).strip()
        action = str(data.get("action", "") or data.get("signal", "ALERT")).strip().upper()
        timeframe = str(data.get("timeframe", "") or data.get("interval", "لحظي")).strip()
        
        entry_price = str(data.get("entry_price", "") or data.get("price", "N/A")).strip()
        entry_time = str(data.get("entry_time", "فور إطلاق التنبيه")).strip()
        
        tp1 = str(data.get("tp1", "N/A")).strip()
        tp2 = str(data.get("tp2", "غير محدد")).strip()
        tp3 = str(data.get("tp3", "غير محدد")).strip()
        
        sl = str(data.get("sl", "N/A")).strip()
        exit_time = str(data.get("exit_time", "عند تحقق الهدف أو وقف الخسارة")).strip()

        action_icon = "🟢" if "BUY" in action or "شراء" in action else "🔴" if "SELL" in action or "بيع" in action else "🔵"

        message_text = (
            f"<b>{action_icon} توصية تداول جديدة</b>\n\n"
            f"📌 <b>رمز واسم السهم:</b> <code>{symbol}</code> ({name})\n"
            f"⚡ <b>اتجاه الصفقة:</b> {action}\n"
            f"⏱️ <b>الإطار الزمني:</b> {timeframe}\n"
            f"💰 <b>نطاق سعر ووقت الدخول:</b> ${entry_price} | {entry_time}\n\n"
            f"🎯 <b>الهدف الأول:</b> {tp1}\n"
            f"🎯 <b>الهدف الثاني:</b> {tp2}\n"
            f"🎯 <b>الهدف الثالث:</b> {tp3}\n\n"
            f"🛑 <b>سعر وقف الخسارة:</b> {sl}\n"
            f"⏳ <b>وقت الخروج المقترح:</b> {exit_time}"
        )

        sent = send_telegram_msg(message_text)
        if sent:
            return jsonify({"status": "success", "message": "Alert sent"}), 200
        else:
            return jsonify({"status": "error", "message": "Telegram failed"}), 500

    except Exception as err:
        return jsonify({"status": "error", "message": str(err)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
