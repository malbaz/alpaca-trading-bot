import os
import requests
from flask import Flask, request, jsonify
from order_manager import order_manager
from risk_engine import risk_engine

app = Flask(__name__)

# ---------------------------------------------------------
# الإعدادات الحماية والتنبيهات
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
WEBHOOK_SECRET = "Murray@@2026++"

def send_telegram_msg(msg_text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg_text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"خطأ تليجرام: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload"}), 400

        # 1. التحقق من كلمة سر التنبيه
        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        symbol = str(data.get("symbol", "")).upper()
        action = str(data.get("action", "")).lower()
        price = float(data.get("price", 0.0))
        bid = float(data.get("bid", price * 0.999))
        ask = float(data.get("ask", price * 1.001))

        if not symbol or price <= 0:
            return jsonify({"status": "error", "message": "Invalid symbol or price"}), 400

        # --- تنفيذ الشراء عبر OrderManager & RiskEngine ---
        if action == "buy":
            # 2. فحص المخاطر أولاً (Daily Loss Limit + Spread)
            if not risk_engine.is_trade_allowed(symbol, bid, ask):
                send_telegram_msg(f"🛑 <b>تنبيه مرفوض من محرك المخاطر:</b> {symbol} (تجاوز السبريد أو حد الخسارة اليومي)")
                return jsonify({"status": "rejected", "reason": "Risk check failed"}), 400

            # 3. إرسال أمر الشراء لـ OrderManager الموحد
            result = order_manager.process_buy_signal(symbol, price, budget=50.0)

            if result.get("status") == "executed":
                msg = (
                    f"📡 <b>إشارة شـراء TradingView (منفذة آلياً)</b>\n\n"
                    f"📌 <b>الرمز:</b> <code>{symbol}</code>\n"
                    f"🎯 <b>السعر:</b> ${price:.2f}\n"
                    f"📦 <b>الكمية:</b> {result.get('qty')} سهم\n"
                    f"🆔 <b>رقم الأمر المحمي:</b> <code>{result.get('order_id')}</code>\n"
                )
                send_telegram_msg(msg)
                return jsonify(result), 200
            else:
                send_telegram_msg(f"⚠️ <b>رفض الشراء لـ {symbol}:</b> {result.get('reason')}")
                return jsonify(result), 400

        # --- تنفيذ البيع عبر OrderManager الموحد ---
        elif action == "sell":
            result = order_manager.process_sell_signal(symbol, price, reason="TradingView Alert")
            if result.get("status") == "executed":
                msg = (
                    f"🚨 <b>إشارة بـيع TradingView (منفذة)</b>\n\n"
                    f"📌 <b>الرمز:</b> <code>{symbol}</code>\n"
                    f"🎯 <b>السعر:</b> ${price:.2f}\n"
                    f"📦 <b>الكمية:</b> {result.get('qty')} سهم\n"
                )
                send_telegram_msg(msg)
                return jsonify(result), 200
            else:
                return jsonify(result), 400

    except Exception as e:
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
