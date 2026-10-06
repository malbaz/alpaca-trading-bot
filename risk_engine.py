import os
import yfinance as yf
from alpaca.trading.client import TradingClient

class RiskEngine:
    """
    محرك إدارة المخاطر المتقدم وزر الإيقاف الآلي (Multi-Level Kill Switch)
    """
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "").strip()
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        self.client = TradingClient(self.api_key, self.secret_key, paper=False)
        
        # 1. إعدادات الحدود الصارمة للمخاطرة
        self.max_spread_pct = 0.50          # حد أقصى للسبريد 0.5%
        self.max_daily_loss_pct = 0.02      # حد أقصى للخسارة اليومية 2.0% من رأس المال
        self.risk_per_trade_usd = 2.00      # أقصى مخاطرة مسموحة بالدولار للصفقة الواحدة
        
        # حالة زر الإيقاف الطارئ
        self.kill_switch_active = False

    def check_daily_loss_limit(self) -> bool:
        """
        التحقق من عدم تجاوز حد الخسارة اليومي الكلي (Daily Loss Limit)
        """
        try:
            account = self.client.get_account()
            equity = float(account.equity)
            last_equity = float(account.last_equity)
            
            # حساب التغير اليومي في القيمة الكلية للحساب
            daily_change_pct = (equity - last_equity) / last_equity
            
            if daily_change_pct <= -self.max_daily_loss_pct:
                self.kill_switch_active = True
                print(f"🚨 [KILL SWITCH] تم تفعيل زر الإيقاف الطارئ! الخسارة اليومية ({daily_change_pct*100:.2f}%) تجاوزت الحد المسموح (-{self.max_daily_loss_pct*100:.1f}%)")
                return False
                
            return True
        except Exception as e:
            print(f"❌ خطأ أثناء فحص حد الخسارة اليومي: {e}")
            return False

    def validate_spread(self, bid: float, ask: float) -> bool:
        """
        فحص الفارق بين العرض والطلب لتجنب التكاليف الخفية
        """
        if bid <= 0 or ask <= 0:
            return False
            
        spread_pct = ((ask - bid) / bid) * 100
        if spread_pct > self.max_spread_pct:
            print(f"⚠️ [رفض الصفقة] السبريد مرتفع جداً ({spread_pct:.2f}% > {self.max_spread_pct}%)")
            return False
            
        return True

    def calculate_position_size(self, symbol: str, current_price: float, atr_value: float) -> int:
        """
        حساب حجم المركز تلقائياً بناءً على تذبذب السهم (ATR) والمخاطرة المحددة بالدولار
        """
        try:
            # استخدام مسافة وقف الخسارة بناءً على 1.5 * ATR
            stop_distance = max(atr_value * 1.5, current_price * 0.015) # حد أدنى 1.5% للمسافة
            
            # الكمية = أقصى مخاطرة بالدولار / مسافة الوقف بالسهم
            qty = int(self.risk_per_trade_usd / stop_distance)
            
            # التأكد من عدم تجاوز الحد الأقصى لميزانية الصفقة ($50.00)
            max_qty_by_budget = int(50.0 / current_price)
            final_qty = min(qty, max_qty_by_budget)
            
            return max(1, final_qty)
        except Exception as e:
            print(f"❌ خطأ حساب حجم المركز لـ {symbol}: {e}")
            return 1

    def is_trade_allowed(self, symbol: str, bid: float, ask: float) -> bool:
        """
        فحص كلي شامل قبل الإذن بإرسال أي أمر شراء
        """
        if self.kill_switch_active:
            print(f"🛑 [مرفوض] النظام في حالة تجميد طارئ (Kill Switch Active).")
            return False

        if not self.check_daily_loss_limit():
            return False

        if not self.validate_spread(bid, ask):
            return False

        return True

risk_engine = RiskEngine()
