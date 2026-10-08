import os
import sys
from flask import Flask, request, jsonify
from order_manager import order_manager

app = Flask(__name__)

# جلب كلمة السر أو القبول التلقائي
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "mysecret123").strip()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "message": "Server is running"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True) or {}
        
        # تحقق مرن يتضمن القبول إذا كانت الكلمة مطابقة أو فارغة للتجربة
        incoming_pass = str(data.get("passphrase", "") or data.get("secret", "") or data.get("token", "")).strip()
        
        if WEBHOOK_PASSPHRASE and incoming_pass != WEBHOOK_PASSPHRASE:
            print(f"⚠️ رفض طلب Webhook: الكلمة المرسلة ({incoming_pass}) غير مطابقة لـ ({WEBHOOK_PASSPHRASE})", flush=True)
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        ticker = data.get("ticker") or data.get("symbol")
        action = (data.get("action") or data.get("side") or "").lower()
        price = float(data.get("price", 0))
        quantity = int(data.get("quantity") or data.get("qty") or 1)

        if not ticker or not action:
            return jsonify({"status": "error", "message": "Missing ticker or action"}), 400

        print(f"📥 [Webhook Signal Received] {ticker} | Action: {action} | Price: {price} | Qty: {quantity}", flush=True)

        if action == "buy":
            result = order_manager.process_buy_signal(ticker, price, budget=50.0)
            return jsonify({"status": "success", "result": result}), 200
        elif action == "sell":
            result = order_manager.close_position(ticker)
            return jsonify({"status": "success", "result": result}), 200
        else:
            return jsonify({"status": "error", "message": f"Unknown action {action}"}), 400

    except Exception as e:
        print(f"❌ خطأ في معالجة الـ Webhook: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
