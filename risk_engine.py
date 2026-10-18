"""
محرك المخاطر: يُسأل قبل كل عملية شراء.
- حد الخسارة اليومية (Kill Switch) — ويُغلق المراكز عند تفعيله.
- قاعدة PDT للحسابات الأقل من 25 ألف دولار.
- عدد صفقات يومي أقصى.
نتيجة فحص الحساب تُخزَّن مؤقتاً لتفادي استنزاف حد طلبات Alpaca.
"""
import logging
import time
from typing import Tuple

import alerts
import state
from config import settings

log = logging.getLogger("risk")


class RiskEngine:
    def __init__(self, broker_trading):
        self.client = broker_trading
        self.kill_switch = False
        self._acct = None
        self._acct_ts = 0.0

    def account(self, max_age: float = 20.0):
        if self._acct is None or time.time() - self._acct_ts > max_age:
            self._acct = self.client.get_account()
            self._acct_ts = time.time()
        return self._acct

    def check_daily_loss(self) -> bool:
        a = self.account()
        equity, last = float(a.equity), float(a.last_equity)
        if last <= 0:
            return True
        change = (equity - last) / last * 100
        if change <= -settings.max_daily_loss_pct and not self.kill_switch:
            self.kill_switch = True
            log.error("KILL SWITCH: daily change %.2f%%", change)
            alerts.system(f"تفعيل الإيقاف الطارئ: الخسارة اليومية {change:.2f}%. سيتم إغلاق كل المراكز.")
            try:
                self.client.cancel_orders()
                self.client.close_all_positions(cancel_orders=True)
            except Exception as e:
                log.error("close_all failed: %s", e)
        return not self.kill_switch

    def check_pdt(self) -> bool:
        a = self.account()
        if float(a.equity) >= 25000:
            return True
        # حساب نقدي (multiplier=1) لا يخضع لـ PDT
        if str(getattr(a, "multiplier", "1")) == "1":
            return True
        if getattr(a, "pattern_day_trader", False):
            return False
        return int(getattr(a, "daytrade_count", 0) or 0) < 3

    def allow_entry(self) -> Tuple[bool, str]:
        if self.kill_switch:
            return False, "الإيقاف الطارئ مفعّل"
        try:
            if not self.check_daily_loss():
                return False, "تجاوز حد الخسارة اليومية"
            if not self.check_pdt():
                return False, "قاعدة PDT: لا مزيد من الصفقات اليومية"
            if bool(getattr(self.account(), "trading_blocked", False)):
                return False, "الحساب محظور من التداول"
        except Exception as e:
            # عند الشك لا نشتري
            return False, f"تعذر فحص الحساب: {e}"
        if state.buys_today() >= settings.max_trades_per_day:
            return False, "تم بلوغ الحد اليومي للصفقات"
        return True, "ok"
