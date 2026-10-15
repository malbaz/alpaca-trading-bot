import os
import time
import uuid
import threading
from typing import Dict, Any, Optional
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

class OrderManager:
    """
    مدير الأوامر الموحد: إدارة حالة التداول والحد المالي لعملية الشراء
    """
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "").strip()
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        self.paper = True

        if not self.api_key or not self.secret_key:
            raise ValueError("مفاتيح Alpaca غير متوفرة في OrderManager.")

        self.client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        
        # قفل الأمان للتعامل مع الطلبات المتوازية
        self.lock = threading.Lock()
        
        # تتبع حالة المراكز المفتوحة
        self.symbol_states: Dict[str, str] = {}
        self.max_concurrent_positions = 3

    def get_symbol_state(self, symbol: str) -> str:
        with self.lock:
            return self.symbol_states.get(symbol.upper(), "NONE")

    def set_symbol_state(self, symbol: str, state: str):
        with self.lock:
            self.symbol_states[symbol.upper()] = state
            print(f"🔄 [{symbol.upper()}] تغيرت الحالة إلى -> {state}")

    def reconcile_positions(self):
        """
        مزامنة المراكز الحقيقية مع ذاكرة البوت
        """
        try:
            positions = self.client.get_all_positions()
            active_symbols = {p.symbol.upper(): "OPEN_POSITION" for p in positions}
            
            with self.lock:
                for sym, state in list(self.symbol_states.items()):
                    if state == "OPEN_POSITION" and sym not in active_symbols:
                        self.symbol_states[sym] = "NONE"
                for sym in active_symbols:
                    self.symbol_states[sym] = "OPEN_POSITION"
            
            print(f"✅ [المزامنة] تم تحديث حالة المراكز المفتوحة: {list(active_symbols.keys())}")
        except Exception as e:
            print(f"❌ [المزامنة] خطأ أثناء المزامنة: {e}")

    def process_buy_signal(self, symbol: str, price: float, budget: float = 25.0) -> Dict[str, Any]:
        """
        معالجة إشارة الشراء مع فحص السعر لمنع القسمة على صفر
        """
        symbol = symbol.upper()
        
        with self.lock:
            # 1. التثبت من المراكز المفتوحة
            open_count = sum(1 for s in self.symbol_states.values() if s in ["PENDING_BUY", "OPEN_POSITION"])
            if open_count >= self.max_concurrent_positions:
                return {"status": "rejected", "reason": f"تم الوصول للحد الأقصى للمراكز المفتوحة ({self.max_concurrent_positions})"}
            
            current_state = self.symbol_states.get(symbol, "NONE")
            if current_state != "NONE":
                return {"status": "rejected", "reason": f"السهم في حالة {current_state} بالفعل"}
            
            self.symbol_states[symbol] = "PENDING_BUY"

        try:
            account = self.client.get_account()
            buying_power = float(account.buying_power)
            actual_budget = min(budget, buying_power)
            
            if actual_budget < 10.0:
                self.set_symbol_state(symbol, "NONE")
                return {"status": "rejected", "reason": f"القوة الشرائية غير كافية ({buying_power}$)"}

            # --- فحص السعر لتفادي القسمة على صفر ---
            if price <= 0:
                try:
                    latest_trade = self.client.get_latest_trade(symbol)
                    price = float(latest_trade.price)
                except Exception as e:
                    print(f"❌ تعذر جلب السعر اللحظي لـ {symbol}: {e}")
                    self.set_symbol_state(symbol, "NONE")
                    return {"status": "rejected", "reason": "Invalid or zero price"}

            qty = int(actual_budget / price)
            if qty <= 0:
                qty = 1  # ضمان شراء سهم واحد على الأقل للأسهم مرتفعة السعر

            limit_price = round(price * 1.005, 2)
            client_order_id = f"bot_buy_{symbol}_{int(time.time())}_{uuid.uuid4().hex[:4]}"

            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
                extended_hours=True,
                client_order_id=client_order_id
            )

            order = self.client.submit_order(order_data)
            self.set_symbol_state(symbol, "OPEN_POSITION")
            print(f"🚀 [شراء] تم إرسال أمر الشراء لـ {symbol} | الكمية: {qty} | السعر: {limit_price} | Order ID: {order.id}")
            return {"status": "executed", "order_id": str(order.id), "qty": qty, "price": limit_price}

        except Exception as e:
            self.set_symbol_state(symbol, "NONE")
            print(f"❌ [خطأ الشراء] {e}")
            return {"status": "error", "reason": str(e)}

    def process_sell_signal(self, symbol: str, price: float, reason: str = "Signal") -> Dict[str, Any]:
        """
        معالجة إشارة الخروج والبيع
        """
        symbol = symbol.upper()
        
        with self.lock:
            current_state = self.symbol_states.get(symbol, "NONE")
            if current_state == "PENDING_SELL":
                return {"status": "rejected", "reason": "يتم البيع بالفعل"}
            
            self.symbol_states[symbol] = "PENDING_SELL"

        try:
            positions = self.client.get_all_positions()
            target_pos = next((p for p in positions if p.symbol.upper() == symbol), None)
            
            if not target_pos:
                self.set_symbol_state(symbol, "NONE")
                return {"status": "rejected", "reason": f"لا يوجد مركز مفتوح لـ {symbol}"}

            qty = int(float(target_pos.qty))
            limit_price = round(price * 0.995, 2)
            client_order_id = f"bot_sell_{symbol}_{int(time.time())}_{uuid.uuid4().hex[:4]}"

            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
                extended_hours=True,
                client_order_id=client_order_id
            )

            order = self.client.submit_order(order_data)
            self.set_symbol_state(symbol, "NONE")
            print(f"📉 [بيع] تم إرسال أمر البيع لـ {symbol} | الكمية: {qty} | السعر: {limit_price}")
            return {"status": "executed", "order_id": str(order.id), "qty": qty, "price": limit_price}

        except Exception as e:
            self.set_symbol_state(symbol, "OPEN_POSITION")
            print(f"❌ [خطأ البيع] {e}")
            return {"status": "error", "reason": str(e)}

order_manager = OrderManager()
