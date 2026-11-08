"""
استقبال إشارات خارجية (مثل TradingView) — تمر بنفس محرك المخاطر ومدير الأوامر.
كلمة السر إلزامية، ولا تُطبع في السجلات.
"""
import hmac
import logging

from flask import Flask, request, jsonify

import broker
from config import settings

log = logging.getLogger("webhook")


def create_app(orders):
    app = Flask(__name__)

    @app.get("/")
    def health():
        return jsonify({"status": "online", "paper": settings.paper}), 200

    @app.post("/webhook")
    def webhook():
        data = request.get_json(silent=True) or {}
        incoming = str(data.get("passphrase") or request.headers.get("X-Webhook-Secret") or "")
        if not settings.webhook_passphrase or not hmac.compare_digest(incoming, settings.webhook_passphrase):
            log.warning("unauthorized webhook from %s", request.remote_addr)
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        symbol = str(data.get("ticker") or data.get("symbol") or "").upper().strip()
        action = str(data.get("action") or data.get("side") or "").lower().strip()
        if not symbol.isalpha() or len(symbol) > 6 or action not in ("buy", "sell", "close"):
            return jsonify({"status": "error", "message": "invalid ticker/action"}), 400

        try:
            phase = broker.market_phase()
            snap = broker.snapshots([symbol]).get(symbol)
            if not snap or not snap.latest_quote:
                return jsonify({"status": "error", "message": "no market data"}), 400
            q = snap.latest_quote
            price = float(snap.latest_trade.price) if snap.latest_trade else float(q.ask_price)
            if action == "buy":
                res = orders.buy(symbol, price, float(q.ask_price or price), phase, source="webhook")
            else:
                res = orders.sell(symbol, "إشارة Webhook", ref_price=float(q.bid_price or price), phase=phase)
            return jsonify({"status": "ok", "result": res}), 200
        except Exception as e:
            log.exception("webhook error")
            return jsonify({"status": "error", "message": str(e)}), 500

    return app
