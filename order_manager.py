"""
مدير الأوامر: الدخول والخروج والمطابقة مع Alpaca.

- الجلسة الرسمية: أمر Bracket (شراء + هدف + وقف) محفوظ لدى Alpaca نفسها،
  فيعمل الوقف حتى لو توقف البوت.
- الوقف المتحرك: عند ربح TRAIL_ACTIVATE_PCT يُلغى الـ Bracket ويُستبدل
  بأمر Stop محفوظ لدى Alpaca عند التعادل، ثم يُرفع مع صعود السعر.
  الأمر محفوظ لدى Alpaca لذا تبقى الحماية حتى لو توقف البوت.
- التداول الممتد: Alpaca لا تدعم Bracket ولا أوامر Stop، فنستخدم Limit
  ويراقب المحرك الهدف والوقف كل دورة (معطّل افتراضيًا من الإعدادات).
"""
import logging
import time
import uuid
from typing import Dict, Any

from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, TakeProfitRequest, StopLossRequest,
    GetOrdersRequest, ReplaceOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus

import alerts
import signals
import state
import strategy
from config import settings

log = logging.getLogger("orders")


class OrderManager:
    def __init__(self, broker_trading, risk):
        self.client = broker_trading
        self.risk = risk

    # ---------- الدخول ----------
    def buy(self, symbol: str, price: float, ask: float, phase: str, source: str = "scanner") -> Dict[str, Any]:
        symbol = symbol.upper()
        ok, reason = self.risk.allow_entry()
        if not ok:
            return {"status": "rejected", "reason": reason}
        if phase == "CLOSED":
            return {"status": "rejected", "reason": "السوق مغلق"}
        if phase == "EXTENDED" and not settings.trade_extended_hours:
            return {"status": "rejected", "reason": "التداول الممتد معطل"}
        if not state.try_reserve(symbol, settings.max_open_positions):
            return {"status": "rejected", "reason": "السهم محجوز/فترة تهدئة/بلغنا حد المراكز"}

        try:
            bp = float(self.risk.account(max_age=5).buying_power)
            # حد أعلى للسعر: أفضل عرض بيع + هامش بسيط، وليس سعر آخر صفقة
            limit = round(max(ask, price) * 1.003, 2)
            qty = strategy.position_qty(limit, bp, settings)
            if qty <= 0:
                state.clear(symbol)
                return {"status": "rejected", "reason": f"الميزانية/المخاطرة لا تسمح (القوة الشرائية ${bp:.2f})"}

            target, stop = strategy.exit_levels(limit, settings)
            coid = f"bot-{symbol}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

            if phase == "REGULAR":
                req = LimitOrderRequest(
                    symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                    limit_price=limit, order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=target),
                    stop_loss=StopLossRequest(stop_price=stop),
                    client_order_id=coid,
                )
            else:
                req = LimitOrderRequest(
                    symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                    limit_price=limit, extended_hours=True, client_order_id=coid,
                )

            order = self.client.submit_order(req)
            state.upsert(symbol, state="PENDING_BUY", qty=qty, target=target, stop=stop,
                         order_id=str(order.id), client_order_id=coid,
                         bracket=1 if phase == "REGULAR" else 0,
                         trailing=0, peak_price=0, stop_order_id=None)
            log.info("BUY submitted %s qty=%s limit=%s phase=%s src=%s", symbol, qty, limit, phase, source)
            return {"status": "submitted", "order_id": str(order.id), "qty": qty, "limit": limit}
        except Exception as e:
            state.clear(symbol)
            log.error("buy error %s: %s", symbol, e)
            return {"status": "error", "reason": str(e)}

    # ---------- الخروج ----------
    def sell(self, symbol: str, reason: str, ref_price: float = 0.0, phase: str = "REGULAR") -> Dict[str, Any]:
        symbol = symbol.upper()
        row = state.get(symbol)
        if row and row["state"] == "PENDING_SELL":
            return {"status": "rejected", "reason": "البيع جارٍ بالفعل"}
        try:
            # إلغاء أي أوامر معلقة (أرجل الـ Bracket أو أمر الوقف المتحرك) قبل البيع
            open_orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
            for o in open_orders:
                self.client.cancel_order_by_id(o.id)

            pos = next((p for p in self.client.get_all_positions() if p.symbol == symbol), None)
            if not pos:
                state.clear(symbol)
                return {"status": "rejected", "reason": "لا يوجد مركز"}

            qty = float(pos.qty)
            state.upsert(symbol, state="PENDING_SELL")
            if phase == "REGULAR":
                # في الجلسة الرسمية: إغلاق فوري بسعر السوق
                self.client.close_position(symbol)
            else:
                px = ref_price or float(pos.current_price)
                # في الممتد: Limit بخصم أكبر عند الوقف لضمان التنفيذ
                discount = 0.985 if "وقف" in reason else 0.997
                self.client.submit_order(LimitOrderRequest(
                    symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                    limit_price=round(px * discount, 2), extended_hours=True,
                    client_order_id=f"bot-exit-{symbol}-{int(time.time())}",
                ))
            log.info("SELL submitted %s qty=%s reason=%s", symbol, qty, reason)
            state.upsert(symbol, order_id=reason)  # نحفظ السبب لرسالة الإغلاق
            return {"status": "submitted", "qty": qty}
        except Exception as e:
            state.upsert(symbol, state="OPEN")
            log.error("sell error %s: %s", symbol, e)
            return {"status": "error", "reason": str(e)}

    # ---------- الوقف المتحرك ----------
    def activate_trailing(self, symbol: str, partial: bool = False):
        """يُلغي أرجل الـ Bracket ويضع أمر Stop محفوظًا لدى Alpaca عند التعادل.

        يُستدعى عندما يبلغ الربح TRAIL_ACTIVATE_PCT. بعدها يرفع المحرك
        الوقف عبر update_trailing مع صعود السعر، ولا ينزله أبدًا.
        عند الفشل يبقى الـ Bracket الأصلي كما هو (لا فقدان للحماية).
        """
        symbol = symbol.upper()
        row = state.get(symbol)
        if not row or row["state"] != "OPEN" or row.get("trailing"):
            return
        try:
            open_orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
            for o in open_orders:
                self.client.cancel_order_by_id(o.id)
            # انتظر حتى تُحرَّر الأسهم من الأوامر الملغاة (حتى 10 ثوانٍ)
            entry = float(row["entry_price"])
            qty = float(row["qty"])
            try:
                # الكمية الفعلية لدى Alpaca هي المرجع (قد تتغير بعد بيع جزئي)
                qty = float(self.client.get_open_position(symbol).qty)
            except Exception:
                pass
            released = False
            for _ in range(20):
                time.sleep(0.5)
                still = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
                try:
                    avail = float(self.client.get_open_position(symbol).qty_available or 0)
                except Exception:
                    avail = 0.0
                if not still and avail >= qty:
                    released = True
                    break
            if not released:
                log.warning("activate_trailing %s: shares not released yet, retry next cycle", symbol)
                return
            breakeven = round(entry * strategy.BREAKEVEN_BUFFER, 2)
            sold = 0
            if partial:
                sold = strategy.partial_qty(qty, settings)
                if sold > 0:
                    # بيع جزء الكمية فورًا بسعر السوق لتأمين المكسب
                    self.client.submit_order(MarketOrderRequest(
                        symbol=symbol, qty=sold, side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                        client_order_id=f"bot-partial-{symbol}-{int(time.time())}",
                    ))
                    state.upsert(symbol, partial_done=1)
                    log.info("partial take-profit %s sold=%s of %s", symbol, sold, qty)
            remaining = qty - sold
            order = self.client.submit_order(StopOrderRequest(
                symbol=symbol, qty=remaining, side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC, stop_price=breakeven,
                client_order_id=f"bot-trail-{symbol}-{int(time.time())}",
            ))
            state.upsert(symbol, trailing=1, bracket=0, stop=breakeven,
                         stop_order_id=str(order.id))
            log.info("trailing activated %s entry=%s stop=%s", symbol, entry, breakeven)
            if sold:
                alerts.system(f"💰 {symbol}: جني ربح جزئي — بيع {sold} سهم، والباقي {remaining:g} بوقف متحرك (الوقف عند التعادل {breakeven}$)")
            else:
                alerts.system(f"🔒 {symbol}: تفعيل الوقف المتحرك — الوقف عند التعادل {breakeven}$ والربح محمي")
        except Exception as e:
            log.error("activate_trailing %s: %s", symbol, e)

    def update_trailing(self, symbol: str, new_stop: float):
        """يرفع أمر الوقف المتحرك لدى Alpaca. لا يُنزِل الوقف أبدًا."""
        symbol = symbol.upper()
        row = state.get(symbol)
        if not row or not row.get("stop_order_id"):
            return
        new_stop = round(new_stop, 2)
        if new_stop <= float(row.get("stop") or 0) + 0.005:
            return  # لا تغيير يستحق أو محاولة إنزال
        try:
            self.client.replace_order_by_id(
                row["stop_order_id"], ReplaceOrderRequest(stop_price=new_stop))
            state.upsert(symbol, stop=new_stop)
            log.info("trailing stop raised %s -> %s", symbol, new_stop)
        except Exception as e:
            log.warning("update_trailing %s: %s", symbol, e)

    # ---------- تحديثات Alpaca اللحظية (trade_updates) ----------
    async def on_trade_update(self, data):
        event = data.event if isinstance(data.event, str) else data.event.value
        o = data.order
        symbol = o.symbol.upper()
        side = o.side if isinstance(o.side, str) else o.side.value
        row = state.get(symbol) or {}

        if event == "fill":
            px = float(o.filled_avg_price or 0)
            qty = float(o.filled_qty or 0)
            if side == "buy":
                target, stop = strategy.exit_levels(px, settings)
                if row.get("bracket"):
                    # أرجل الـ Bracket محسوبة من سعر الحد؛ نعرضها كما هي
                    target, stop = row.get("target", target), row.get("stop", stop)
                state.upsert(symbol, state="OPEN", qty=qty, entry_price=px,
                             target=target, stop=stop, peak_price=px)
                state.log_trade(symbol, "buy", qty, px, "entry")
                alerts.entry_filled(symbol, qty, px, target, stop, "رسمية" if row.get("bracket") else "ممتد")
                # توصية لمجموعة العملاء — معزولة تمامًا: أي خطأ هنا لا يؤثر على التداول
                try:
                    signals.send_signal(symbol, px, stop, target)
                except Exception as sig_err:
                    log.warning("signals: فشل إرسال التوصية (%s) — التداول مستمر", sig_err)
            elif str(getattr(o, "client_order_id", "") or "").startswith("bot-partial-"):
                # بيع جزئي: المركز ما زال مفتوحًا بالكمية الباقية
                entry = float(row.get("entry_price") or 0)
                left = max(0.0, float(row.get("qty") or 0) - qty)
                state.log_trade(symbol, "sell", qty, px, "جني ربح جزئي")
                state.upsert(symbol, qty=left)
                pnl = (px - entry) * qty
                alerts.system(f"💰 {symbol}: تم بيع {qty:g} سهم عند {px}$ (ربح {pnl:+.2f}$) — الباقي {left:g} يركب الموجة")
            else:
                reason = row.get("order_id") if row.get("state") == "PENDING_SELL" else "هدف/وقف Alpaca"
                if row.get("trailing") and row.get("state") != "PENDING_SELL":
                    reason = "وقف متحرك"
                state.log_trade(symbol, "sell", qty, px, reason)
                alerts.exit_filled(symbol, qty, row.get("entry_price", 0), px, reason)
                state.clear(symbol)
                state.set_cooldown(symbol, settings.symbol_cooldown_min)
        elif event == "partial_fill" and side == "buy":
            state.upsert(symbol, qty=float(o.filled_qty or 0))
        elif event in ("canceled", "expired", "rejected"):
            if side == "buy" and row.get("state") == "PENDING_BUY":
                if float(o.filled_qty or 0) > 0:
                    state.upsert(symbol, state="OPEN", qty=float(o.filled_qty),
                                 entry_price=float(o.filled_avg_price or 0))
                else:
                    state.clear(symbol)
            elif side == "sell" and row.get("state") == "PENDING_SELL":
                state.upsert(symbol, state="OPEN")
            log.info("order %s %s %s", event, side, symbol)

    # ---------- الصيانة الدورية ----------
    def cancel_stale_entries(self):
        for row in state.active():
            if row["state"] == "PENDING_BUY" and time.time() - (row["updated_at"] or 0) > settings.entry_timeout_sec:
                try:
                    if row.get("order_id"):
                        self.client.cancel_order_by_id(row["order_id"])
                except Exception as e:
                    log.warning("cancel stale %s: %s", row["symbol"], e)

    def reconcile(self):
        """مطابقة قاعدة البيانات مع المراكز الفعلية في Alpaca (Alpaca هي المرجع)."""
        positions = {p.symbol.upper(): p for p in self.client.get_all_positions()}
        for row in state.active():
            if row["state"] == "OPEN" and row["symbol"] not in positions:
                state.clear(row["symbol"])
        for sym, p in positions.items():
            row = state.get(sym)
            if not row or row["state"] == "NONE":
                entry = float(p.avg_entry_price)
                target, stop = strategy.exit_levels(entry, settings)
                state.upsert(sym, state="OPEN", qty=float(p.qty), entry_price=entry,
                             target=target, stop=stop, peak_price=float(p.current_price or entry))
