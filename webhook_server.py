import os
import requests
from flask import Flask, request, jsonify
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

app = Flask(__name__)

# ---------------------------------------------------------
# 1. الإعدادات والربط
# ---------------------------------------------------------

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# كلمة السر الخاصة بالتحقق من أمان TradingView Webhook
WEBHOOK_SECRET = "Murray@@2026++"

# الميزانية ونسب وقف الخسارة المحدثة
TARGET_TRADE_AMOUNT_USD = 50.0 # خفض ميزانية الصفقة إلى 50.00$
QUICK_TAKE_PROFIT_PCT = 0.045  # هدف خروج +4.5%
STOP_LOSS_PCT = 0.025          # وقف خسارة مشدد -2.5%

trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=False)

# ---------------------------------------------------------
# 2. دالة إرسال تنبيهات التليجرام
# ---------------------------------------------------------

def send_telegram_msg(msg_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg_text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"خطأ تليجرام: {e}")

# ---------------------------------------------------------
# 3. نقطة استقبال التنبيهات (Webhook Endpoint)
# ---------------------------------------------------------

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload received"}), 400

        # التحقق من كلمة السر للحماية
        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({"status": "error", "message": "Unauthorized secret"}), 401

        symbol = str(data.get("symbol", "")).upper()
        action = str(data.get("action", "")).lower() # buy أو sell
        price = float(data.get("price", 0.0))

        if not symbol or not price:
            return jsonify({"status": "error", "message": "Invalid symbol or price"}), 400

        # --- حالة تنفيذ الشراء (BUY) ---
        if action == "buy":
            account = trading_client.get_account()
            buying_power = float(account.buying_power)
            trade_budget = min(TARGET_TRADE_AMOUNT_USD, buying_power)

            if trade_budget < 15.0:
                send_telegram_msg(f"⚠️ <b>TradingView Signal:</b> القوة الشرائية غير كافية للشراء في {symbol}.")
                return jsonify({"status": "error", "message": "Insufficient funds"}), 400

            qty = max(1, int(trade_budget / price))
            limit_price = round(price * 1.002, 2)

            order = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
                extended_hours=True
            )
            trading_client.submit_order(order)

            # حساب الأهداف للتنبيه
            target_fast = round(price * (1 + QUICK_TAKE_PROFIT_PCT), 2)
            stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)

            msg = (
                f"📡 <b>إشارة تنبيه TradingView (شراء)</b>\n\n"
                f"📌 <b>الرمز:</b> <code>{symbol}</code>\n"
                f"🎯 <b>سعر الدخول:</b> ${price:.2f}\n"
                f"💵 <b>الميزانية المخصصة:</b> ${trade_budget:.2f} (عدد {qty} سهم)\n"
                f"🚀 <b>هدف الربح الخاطف (+4.5%):</b> ${target_fast:.2f}\n"
                f"🚨 <b>وقف الخسارة (-2.5%):</b> ${stop_loss:.2f}\n"
            )
            send_telegram_msg(msg)
            return jsonify({"status": "success", "action": "buy_executed", "symbol": symbol, "qty": qty}), 200

        # --- حالة تنفيذ البيع / الخروج (SELL) ---
        elif action == "sell":
            positions = trading_client.get_all_positions()
            for pos in positions:
                if pos.symbol == symbol:
                    qty = float(pos.qty)
                    sell_limit_price = round(price * 0.990, 2)

                    exit_order = LimitOrderRequest(
                        symbol=symbol,
                        qty=qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY,
                        limit_price=sell_limit_price,
                        extended_hours=True
                    )
                    trading_client.submit_order(exit_order)

                    msg = (
                        f"🚨 <b>إشارة خروج TradingView (بيع)</b>\n\n"
                        f"📌 <b>الرمز:</b> <code>{symbol}</code>\n"
                        f"🎯 <b>سعر البيع:</b> ${price:.2f}\n"
                        f"📦 <b>الكمية المباعة:</b> {qty} سهم\n"
                    )
                    send_telegram_msg(msg)
                    return jsonify({"status": "success", "action": "sell_executed", "symbol": symbol}), 200

            return jsonify({"status": "ignored", "message": "No open position to sell"}), 200

    except Exception as e:
        print(f"Webhook Error: {e}")
        send_telegram_msg(f"❌ <b>خطأ تنفيذي في Webhook:</b> {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
