"""
نقطة التشغيل الوحيدة. عملية واحدة تحتوي:
  - المحرك (مسح + إدارة خروج) في Thread
  - بث تحديثات الأوامر من Alpaca (trade_updates) في Thread
  - خادم Webhook (waitress) في الـ Thread الرئيسي
كلها تتشارك نفس الحالة ونفس محرك المخاطر — لا تكرار أوامر.
"""
import logging
import sys
import threading
import time

from config import settings, validate_settings


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", encoding="utf-8")],
    )


def run_trade_stream(orders):
    from alpaca.trading.stream import TradingStream
    log = logging.getLogger("stream")
    while True:
        try:
            stream = TradingStream(settings.api_key, settings.secret_key, paper=settings.paper)
            stream.subscribe_trade_updates(orders.on_trade_update)
            log.info("trade_updates stream connected")
            stream.run()
        except Exception as e:
            log.error("trade stream dropped: %s", e)
        time.sleep(5)


def main():
    setup_logging()
    log = logging.getLogger("main")
    problems = validate_settings()
    if problems:
        for p in problems:
            log.error(p)
        sys.exit(1)

    import broker, state
    from risk_engine import RiskEngine
    from order_manager import OrderManager
    from engine import Engine
    from webhook_server import create_app

    state.init()
    acct = broker.trading.get_account()  # يفشل فوراً إذا كانت المفاتيح لا تطابق البيئة
    log.info("connected | paper=%s | equity=%s | buying_power=%s | PDT=%s | daytrades=%s",
             settings.paper, acct.equity, acct.buying_power, acct.pattern_day_trader, acct.daytrade_count)

    risk = RiskEngine(broker.trading)
    orders = OrderManager(broker.trading, risk)
    orders.reconcile()

    threading.Thread(target=run_trade_stream, args=(orders,), daemon=True, name="stream").start()
    threading.Thread(target=Engine(orders).run_forever, daemon=True, name="engine").start()

    app = create_app(orders)
    if settings.webhook_passphrase:
        from waitress import serve
        log.info("webhook on port %s", settings.port)
        serve(app, host="0.0.0.0", port=settings.port)
    else:
        log.warning("WEBHOOK_PASSPHRASE غير محدد — خادم Webhook معطّل")
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
