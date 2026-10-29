"""
المحرك الموحد — يحل محل screener.py و trading_bot.py و data_stream.py.
دورة واحدة كل SCAN_INTERVAL_SEC:
  1) تحديد مرحلة السوق من ساعة Alpaca
  2) مطابقة المراكز + إلغاء أوامر الشراء المتأخرة
  3) إدارة الخروج: وقف ثابت ثم وقف متحرك بعد ربح TRAIL_ACTIVATE_PCT
  4) البحث عن فرص جديدة بطلبات مجمعة لكل الأسهم

قواعد منع البيع المبكر:
- فحص الخروج على متوسط السعر (mid) وليس سعر الطلب (bid) الذي يهبط لحظيًا.
- لا خروج محلي إذا كان السبريد أوسع من MAX_SPREAD_EXIT_PCT (هبوط وهمي).
- الوقف المتحرك لا ينزل أبدًا: بعد التفعيل أسوأ نتيجة هي التعادل.
"""
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

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
            if row["state"] != "OPEN":
                continue
            symbol = row["symbol"]
            snap = snaps.get(symbol)
            if not snap or not snap.latest_quote:
                continue
            q = snap.latest_quote
            bid = float(q.bid_price or 0)
            ask = float(q.ask_price or 0)
            if bid <= 0 or ask <= 0:
                continue
            # سبريد واسع = أسعار غير موثوقة؛ لا نبيع على هبوط وهمي
            if strategy.spread_pct(bid, ask) > settings.max_spread_exit_pct:
                continue
            mid = (bid + ask) / 2
            entry = float(row["entry_price"] or 0)
            if entry <= 0:
                continue

            # تتبع أعلى سعر وصله السهم منذ الدخول
            peak = max(float(row.get("peak_price") or 0), mid)
            if peak != float(row.get("peak_price") or 0):
                state.upsert(symbol, peak_price=peak)

            # 1) الوقف الثابت الأصلي — الحماية الأولى قبل التفعيل
            if not row.get("trailing") and mid <= float(row.get("stop") or 0):
                change = (mid - entry) / entry * 100
                reason = f"وقف خسارة ({change:.2f}%)"
                log.info("exit %s: %s", symbol, reason)
                self.orders.sell(symbol, reason, ref_price=mid, phase=phase)
                continue

            # 2) تفعيل الوقف المتحرك عند بلوغ ربح TRAIL_ACTIVATE_PCT
            if not row.get("trailing"):
                if strategy.trailing_stop_level(entry, peak, settings) is not None:
                    if phase == "REGULAR":
                        # يستبدل الـ Bracket بأمر Stop محفوظ لدى Alpaca عند التعادل
                        self.orders.activate_trailing(symbol)
                    else:
                        # الممتد: لا أوامر Stop لدى Alpaca — تتبع محلي فقط
                        state.upsert(symbol, trailing=1)
                continue

            # 3) الوقف المتحرك بعد التفعيل
            tstop = strategy.trailing_stop_level(entry, peak, settings)
            if tstop is None:
                continue
            if mid <= tstop:
                change = (mid - entry) / entry * 100
                reason = f"وقف متحرك ({change:+.2f}%)"
                log.info("exit %s: %s", symbol, reason)
                self.orders.sell(symbol, reason, ref_price=mid, phase=phase)
            elif phase == "REGULAR":
                # رفع أمر الوقف المحفوظ لدى Alpaca مع صعود السعر
                self.orders.update_trailing(symbol, tstop)

    @staticmethod
    def entry_window_open(now_et=None) -> bool:
        """الجلسة الرسمية فقط: لا شراء أول SKIP_OPEN_MIN ولا آخر NO_ENTRY_BEFORE_CLOSE_MIN دقيقة."""
        now_et = now_et or datetime.now(ZoneInfo("America/New_York"))
        m = now_et.hour * 60 + now_et.minute
        start = 9 * 60 + 30 + settings.skip_open_min
        end = 16 * 60 - settings.no_entry_before_close_min
        return start <= m < end

    def scan(self, phase: str, snaps):
        if phase == "REGULAR" and not self.entry_window_open():
            return
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
