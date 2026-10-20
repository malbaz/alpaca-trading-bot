"""
المحرك الموحد — يحل محل screener.py و trading_bot.py و data_stream.py.
دورة واحدة كل SCAN_INTERVAL_SEC:
  1) تحديد مرحلة السوق من ساعة Alpaca
  2) مطابقة المراكز + إلغاء أوامر الشراء المتأخرة
  3) إدارة الخروج في التداول الممتد (في الرسمية يتكفل بها Bracket)
  4) البحث عن فرص جديدة بطلبات مجمعة لكل الأسهم
"""
import logging
import time

import alerts
import broker
import state
import strategy
from config import settings

log = logging.getLogger("engine")


class Engine:
    def __init__(self, orders):
        self.orders = orders
        self.running = True

    def manage_exits(self, phase: str, snaps):
        for row in state.active():
            if row["state"] != "OPEN" or row.get("bracket") and phase == "REGULAR":
                continue
            snap = snaps.get(row["symbol"])
            if not snap or not snap.latest_quote:
                continue
            bid = float(snap.latest_quote.bid_price or 0)  # البيع يتم على سعر الطلب
            reason = strategy.should_exit(row["entry_price"], bid, settings)
            if reason:
                log.info("exit %s: %s", row["symbol"], reason)
                self.orders.sell(row["symbol"], reason, ref_price=bid, phase=phase)

    def scan(self, phase: str, snaps):
        if state.active_count() >= settings.max_open_positions:
            return
        candidates = [s for s in settings.watchlist
                      if state.state_of(s) == "NONE" and not state.in_cooldown(s)]
        bars = broker.minute_bars(candidates, minutes=15)
        signals = []
        for sym in candidates:
            b = bars.get(sym) or []
            snap = snaps.get(sym)
            if not b or not snap or not snap.latest_quote:
                continue
            q = snap.latest_quote
            sig = strategy.evaluate(sym, [x.close for x in b], [int(x.volume) for x in b],
                                    float(q.bid_price or 0), float(q.ask_price or 0), settings)
            if sig:
                signals.append(sig)
        # الأقوى زخماً أولاً
        for sig in sorted(signals, key=lambda x: x.momentum_pct, reverse=True):
            res = self.orders.buy(sig.symbol, sig.price, sig.ask, phase)
            log.info("signal %s +%.2f%% vol=%s -> %s", sig.symbol, sig.momentum_pct, sig.volume_10m, res)
            if state.active_count() >= settings.max_open_positions:
                break

    def tick(self):
        phase = broker.market_phase()
        if phase == "CLOSED":
            return phase
        self.orders.reconcile()
        self.orders.cancel_stale_entries()
        symbols = list({*settings.watchlist, *[r["symbol"] for r in state.active()]})
        snaps = broker.snapshots(symbols)
        self.manage_exits(phase, snaps)
        self.scan(phase, snaps)
        return phase

    def run_forever(self):
        alerts.system(f"بدء التشغيل ({'تجريبي' if settings.paper else 'حقيقي'}، بيانات {settings.data_feed.upper()})")
        errors = 0
        while self.running:
            try:
                phase = self.tick()
                errors = 0
                time.sleep(settings.scan_interval_sec if phase != "CLOSED" else 300)
            except Exception as e:
                errors += 1
                log.exception("tick error: %s", e)
                if errors in (3, 20):
                    alerts.system(f"أخطاء متكررة في المحرك: {e}")
                time.sleep(min(60, 5 * errors))
