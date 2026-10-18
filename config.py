"""
config.py — الإعدادات المركزية للبوت
كل القيم تُقرأ من متغيرات البيئة (Railway Variables).
لا تكتب أي مفتاح سري داخل هذا الملف أبدًا.
"""

import os
from dataclasses import dataclass, field


def _env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: list) -> list:
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    # === مفاتيح Alpaca (تُضبط في Railway فقط) ===
    alpaca_api_key: str = field(default_factory=lambda: _env_str("ALPACA_API_KEY"))
    alpaca_secret_key: str = field(default_factory=lambda: _env_str("ALPACA_SECRET_KEY"))

    # === وضع التشغيل ===
    # true = حساب تجريبي (paper) | false = حساب حقيقي
    paper_trading: bool = field(default_factory=lambda: _env_bool("PAPER_TRADING", True))

    # مصدر البيانات: "iex" مجاني | "sip" مدفوع
    data_feed: str = field(default_factory=lambda: _env_str("DATA_FEED", "iex").lower())

    # === قائمة المراقبة ===
    watchlist: list = field(default_factory=lambda: _env_list(
        "WATCHLIST", ["ABTE", "DBRG", "MOBX"]))

    # === فلترة الأسهم ===
    min_price: float = field(default_factory=lambda: _env_float("MIN_PRICE", 5.0))
    max_price: float = field(default_factory=lambda: _env_float("MAX_PRICE", 50.0))
    max_spread_pct: float = field(default_factory=lambda: _env_float("MAX_SPREAD_PCT", 1.0))
    min_volume: int = field(default_factory=lambda: _env_int("MIN_VOLUME", 500_000))

    # === إدارة المخاطر ===
    risk_per_trade_pct: float = field(default_factory=lambda: _env_float("RISK_PER_TRADE_PCT", 1.0))
    stop_loss_pct: float = field(default_factory=lambda: _env_float("STOP_LOSS_PCT", 2.5))
    take_profit_pct: float = field(default_factory=lambda: _env_float("TAKE_PROFIT_PCT", 5.0))
    max_open_positions: int = field(default_factory=lambda: _env_int("MAX_OPEN_POSITIONS", 3))
    max_daily_trades: int = field(default_factory=lambda: _env_int("MAX_DAILY_TRADES", 6))
    max_position_value_pct: float = field(default_factory=lambda: _env_float("MAX_POSITION_VALUE_PCT", 25.0))
    daily_loss_limit_pct: float = field(default_factory=lambda: _env_float("DAILY_LOSS_LIMIT_PCT", 3.0))
    cooldown_minutes: int = field(default_factory=lambda: _env_int("COOLDOWN_MINUTES", 30))

    # === المحرك ===
    scan_interval_seconds: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_SECONDS", 30))
    order_timeout_seconds: int = field(default_factory=lambda: _env_int("ORDER_TIMEOUT_SECONDS", 120))

    # === قاعدة البيانات ===
    db_path: str = field(default_factory=lambda: _env_str("DB_PATH", "bot_state.db"))

    # === تليجرام ===
    telegram_bot_token: str = field(default_factory=lambda: _env_str("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env_str("TELEGRAM_CHAT_ID"))

    # === Webhook (TradingView) ===
    webhook_passphrase: str = field(default_factory=lambda: _env_str("WEBHOOK_PASSPHRASE"))
    webhook_port: int = field(default_factory=lambda: _env_int("PORT", 8080))

    def get_base_url(self) -> str:
        """رابط Alpaca حسب وضع التشغيل."""
        if self.paper_trading:
            return "https://paper-api.alpaca.markets"
        return "https://api.alpaca.markets"


def validate_settings(s: Settings) -> list:
    """يفحص الإعدادات ويرجع قائمة الأخطاء (فارغة = كل شيء سليم)."""
    errors = []
    if not s.alpaca_api_key:
        errors.append("ALPACA_API_KEY غير موجود في متغيرات البيئة")
    if not s.alpaca_secret_key:
        errors.append("ALPACA_SECRET_KEY غير موجود في متغيرات البيئة")
    if not s.webhook_passphrase:
        errors.append("WEBHOOK_PASSPHRASE غير موجود — الـ webhook سيكون مكشوفًا")
    if s.data_feed not in ("iex", "sip"):
        errors.append(f"DATA_FEED يجب أن يكون iex أو sip (الحالي: {s.data_feed})")
    if s.min_price >= s.max_price:
        errors.append("MIN_PRICE يجب أن يكون أقل من MAX_PRICE")
    if s.stop_loss_pct <= 0 or s.take_profit_pct <= 0:
        errors.append("نسب وقف الخسارة وجني الربح يجب أن تكون أكبر من صفر")
    if not s.watchlist:
        errors.append("قائمة المراقبة WATCHLIST فارغة")
    return errors


# نسخة واحدة تُستخدم في كل الملفات
settings = Settings()
