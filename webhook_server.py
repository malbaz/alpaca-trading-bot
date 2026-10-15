import os
import sys
from flask import Flask, request, jsonify
from order_manager import order_manager

app = Flask(__name__)

WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "mysecret123").strip()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "message": "Server is running"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True) or {}
        
        # التحقق من كلمة السر
        incoming_pass = str(data.get("passphrase", "") or data.get("secret", "") or data.get("token", "")).strip()
        
        if WEBHOOK_PASSPHRASE and incoming_pass != WEBHOOK_PASSPHRASE:
            print(f"⚠️ محاولة وصول غير مصرح بها (Pass: '{incoming_pass}')", flush=True)
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        ticker = data.get("ticker") or data.get("symbol")
        action = (data.get("action") or data.get("side") or "").lower()
        price = float(data.get("price", 0))
        quantity = int(data.get("quantity") or data.get("qty") or 1)

        # قراءة الأهداف ووقف الخسارة من الـ Webhook إن وجدت
        target1 = data.get("target1")
        target2 = data.get("target2")
        target3 = data.get("target3")
        stop_loss = data.get("stop_loss")

        if not ticker or not action:
            return jsonify({"status": "error", "message": "Missing ticker or action"}), 400

        print(f"📩 [Webhook Signal Received] {ticker} | Action: {action} | Price: {price}", flush=True)

        if action == "buy":
            result = order_manager.process_buy_signal(
                symbol=ticker, 
                price=price, 
                budget=25.0,
                target1=target1,
                target2=target2,
                target3=target3,
                stop_loss=stop_loss
            )
            return jsonify({"status": "success", "result": result}), 200
        elif action in ["sell", "close"]:
            result = order_manager.process_sell_signal(ticker, price)
            return jsonify({"status": "success", "result": result}), 200
        else:
            return jsonify({"status": "error", "message": f"Unknown action '{action}'"}), 400

    except Exception as e:
        print(f"❌ خطأ في معالجة الـ Webhook: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
