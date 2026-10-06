import os
import yfinance as yf
from alpaca.trading.client import TradingClient

class RiskEngine:
    """
    محرك إدارة المخاطر المتقدم وزر الإيقاف الآلي
    """
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "").strip()
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        self.client = TradingClient(self.api_key, self.secret_key, paper=False)
        
        # 1. إعدادات الحدود الصارمة للمخاطرة
        self.max_spread_pct = 0.50          # حد أقصى للسبريد 0.5%
        self.max_daily_loss_pct = 0.02      # حد أقصى للخسارة اليومية 2.0%
        self.risk_per_trade_usd = 2.00      # أقصى مخاطرة مسموحة بالدولار للصفقة الواحدة
        
        # حالة زر الإيقاف الطارئ
        self.kill_switch_active = False

    def check_daily_loss_limit() -> bool:
        """
        التحقق من عدم تجاوز حد الخسارة اليومي الكلي (Daily Loss Limit)
        """
        try:
            account = self.client.get_account()
            equity = float(account.equity)
            last_
