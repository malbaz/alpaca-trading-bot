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
    مدير الأوامر الموحد وآلة الحالة لمنع التضارب وضمان حماية الحساب
    """
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "").strip()
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        self.paper = False
        
        if not self.api_key or not self.secret_key:
            raise ValueError("مفاتيح Alpaca غير متوفرة لـ OrderManager.")

        self.client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        
        # قفل الأمان للتعامل مع الطلبات المتزامنة (Thread Lock)
        self.lock = threading.Lock()
        
        # ذاكرة آلة الحالة للأسهم (State Machine Tracker)
        # States: "NONE", "PENDING_BUY", "OPEN_POSITION", "PENDING_SELL"
        self.symbol_states: Dict[str, str] = {}
        
        # أقصى عدد صفقات مفتوحة في نفس الوقت لحماية الحساب
        self.max_concurrent_positions = 2

    def get_symbol_state(self, symbol: str) -> str:
        with self.lock:
            return self.symbol_states.get(symbol.upper(), "NONE")

    def set_symbol_state(self, symbol: str, state: str):
        with self.lock:
            self.symbol_states[symbol.upper()] = state
            print(f"🔄 [تحديث الحالة] {symbol.upper()} ➔ {state}")

    def reconcile_positions(self):
        """
        مطابقة ذاكرة البوت مع المراكز الحقيقية لدى الوسيط Alpaca
        """
        try:
            positions = self.client.get_all_positions()
            active_symbols = {p.symbol.upper(): "OPEN_POSITION" for p in positions}
            
            with self.lock:
                # تحديث الأسهم المفتوحة لدى الوسيط
                for sym, state in active_symbols.items():
                    self.symbol_states[sym] = state
                    
                # إعادة ضبط الأسهم غير الموجودة لدى الوسيط كـ NONE
                for sym in list(self.symbol_states.keys()):
                    if self.symbol_states[sym] == "OPEN_POSITION" and sym not in active_symbols:
                        self.symbol_states[sym] = "NONE"
                        
            print(f"✅ [المطابقة] تم تحديث حالة المراكز المفتوحة: {list(active_symbols.keys())}")
        except Exception as e:
            print(f"❌ خطأ أثناء المطابقة مع الوسيط: {e}")

    def process_buy_signal(self, symbol: str, price: float, budget: float = 50.0) -> Dict[str, Any]:
        """
        نافذة التنفيذ الموحدة لجميع إشارات الشراء (سواءً من Webhook أو Screener)
        """
        symbol = symbol.upper()
        
        with self.lock:
            # 1. مطابقة سقف الصفقات المفتوحة
            open_count = sum(1 for s in self.symbol_states.values() if s in ["PENDING_BUY", "OPEN_POSITION"])
            if open_count >= self.max_concurrent_positions:
                return {"status": "rejected", "reason": f"تم الوصول للحد الأقصى للمراكز المتزامنة ({self.max_concurrent_positions})"}

            # 2. فحص حالة السهم لمنع التكرار
            current_state = self.symbol_states.get(symbol, "NONE")
            if current_state != "NONE":
                return {"status": "rejected", "reason": f"السهم {symbol} في حالة {current_state} بالفعل"}

            # حجز السهم مؤقتاً
            self.symbol_states[symbol] = "PENDING_BUY"

        try:
            # 3. التحقق من القوة الشرائية
            account = self.client.get_account()
            buying_power = float(account.buying_power)
            actual_budget = min(budget, buying_power)

            if actual_budget < 15.0:
                self.set_symbol_state(symbol, "NONE")
                return {"status": "rejected", "reason": f"القوة الشرائية غير كافية (${buying_power:.2f})"}

            qty = max(1, int(actual_budget / price))
            limit_price = round(price * 1.002, 2)
            
            # 4. إنشاء معرّف أمر فريد محمي لمنع تكرار الأمر في خوادم Alpaca
            client_order_id = f"bot_buy_{symbol}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

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
            print(f"🚀 [شراء ناجح] {symbol} | الكمية: {qty} | السعر: ${limit_price} | Order ID: {order.id}")
            return {"status": "executed", "order_id": str(order.id), "qty": qty, "price": limit_price}

        except Exception as e:
            self.set_symbol_state(symbol, "NONE")
            print(f"❌ [فشل الشراء] {symbol}: {e}")
            return {"status": "error", "reason": str(e)}

    def process_sell_signal(self, symbol: str, price: float, reason: str = "Signal") -> Dict[str, Any]:
        """
        نافذة التنفيذ الموحدة لجميع إشارات البيع والخروج
        """
        symbol = symbol.upper()
        
        with self.lock:
            current_state = self.symbol_states.get(symbol, "NONE")
            if current_state == "PENDING_SELL":
                return {"status": "rejected", "reason": f"السهم {symbol} قيد البيع بالفعل"}
            
            self.symbol_states[symbol] = "PENDING_SELL"

        try:
            positions = self.client.get_all_positions()
            target_pos = next((p for p in positions if p.symbol.upper() == symbol), None)

            if not target_pos:
                self.set_symbol_state(symbol, "NONE")
                return {"status": "rejected", "reason": f"لا يوجد مركز مفتوح لـ {symbol} لدى الوسيط"}

            qty = int(float(target_pos.qty))
            sell_limit_price = round(price * 0.990, 2)
            client_order_id = f"bot_sell_{symbol}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

            exit_order = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=sell_limit_price,
                extended_hours=True,
                client_order_id=client_order_id
            )

            order = self.client.submit_order(exit_order)
            self.set_symbol_state(symbol, "NONE")
            print(f"✅ [بيع ناجح] {symbol} | السبب: {reason} | الكمية: {qty} | السعر: ${sell_limit_price}")
            return {"status": "executed", "order_id": str(order.id), "qty": qty, "price": sell_limit_price}

        except Exception as e:
            self.set_symbol_state(symbol, "OPEN_POSITION")
            print(f"❌ [فشل البيع] {symbol}: {e}")
            return {"status": "error", "reason": str(e)}

# كائن عالمي موحد لاستخدامه عبر التطبيق
order_manager = OrderManager()
