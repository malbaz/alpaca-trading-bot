"""
config.py — الإعدادات المركزية للبوت (المصدر الوحيد لكل الأرقام)
كل القيم تُقرأ من متغيرات البيئة (Railway Variables).
لا تكتب أي مفتاح سري داخل هذا الملف أبدًا.

اسم الحقل هنا = الاسم الذي تستخدمه بقية الملفات (strategy / risk_engine /
order_manager / engine / alerts / webhook_server / main).
"""
import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ================= قراءات آمنة من متغيرات البيئة =================
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
        return int(float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


# ================= قائمة المراقبة الافتراضية =================
# عدّلها من متغير WATCHLIST في Railway (مفصولة بفواصل).
DEFAULT_WATCHLIST = [
    "BOOM", "BRBR", "BNED", "BOF", "BLZE", "BKKT", "BIAF", "AXIL",
    "AYTU", "AVO", "AVPT", "AMOD", "NSTR", "AIXI", "CYCU", "PMI",
    "AMPL", "AMPX", "ABSI", "AMBO", "AEYE", "AIOT", "AENT", "ADTN",
    "ABEO", "EEIQ", "HSCS", "CVM", "EFOI", "CSAI",
    "LONA", "AZ", "JDZG", "RTB", "LNZA", "MTNB", "IDAI", "AIRG",
    "BMHL", "PICS", "RGC", "HYLN", "FISN", "CJMB", "BTLN", "INTS",
    "DFNS", "OSG", "EP", "CTNT", "DDD", "RXT", "SOC", "CUVL",
    "SOTK", "KOPN", "SHIM", "INDP", "ATRA",
    "ABLV", "WVVI", "SDEV", "GOW", "NNBR", "NAUT", "ICU",
    "REBN", "NEOV", "FEAM", "SSM", "IMC", "CELU", "ONCY", "ABVC",
    "TLSI", "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI",
    "LUNR", "SERV", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP",
    "KULR", "GTEC", "PDSB", "GRML", "BFLY", "EAF", "IPDN", "WFCF", "MOBX",
]


@dataclass
class Settings:
    # === مفاتيح Alpaca (تُضبط في Railway فقط) ===
    api_key: str = field(default_factory=lambda: _env_str("ALPACA_API_KEY"))
    secret_key: str = field(default_factory=lambda: _env_str("ALPACA_SECRET_KEY"))

    # === وضع التشغيل ===
    # true = حساب تجريبي (paper) | false = حساب حقيقي
    # ⚠️ المفاتيح يجب أن تكون من نفس البيئة
    paper: bool = field(default_factory=lambda: _env_bool("PAPER_TRADING", True))

    # مصدر البيانات: "iex" مجاني | "sip" اشتراك مدفوع
    data_feed: str = field(default_factory=lambda: _env_str("DATA_FEED", "iex").lower())

    # === قائمة المراقبة ===
    watchlist: List[str] = field(default_factory=lambda: _env_list(
        "WATCHLIST", DEFAULT_WATCHLIST))

    # === فلترة الأسهم (معايير الدخول) ===
    min_price: float = field(default_factory=lambda: _env_float("MIN_PRICE", 1.50))
    max_price: float = field(default_factory=lambda: _env_float("MAX_PRICE", 16.00))
    # نافذة حساب الزخم بالدقائق
    momentum_window_min: int = field(default_factory=lambda: _env_int("MOMENTUM_WINDOW_MIN", 5))
    # أقل ارتفاع مطلوب خلال النافذة (٪)
    min_momentum_pct: float = field(default_factory=lambda: _env_float("MIN_MOMENTUM_PCT", 3.0))
    # حجم آخر 10 دقائق. على بيانات iex المجانية ابقِه صغيرًا (ترى 2-3٪ من السوق)
    min_volume_10m: int = field(default_factory=lambda: _env_int("MIN_VOLUME_10M", 20000))
    # أقصى فرق بين العرض والطلب (٪)
    max_spread_pct: float = field(default_factory=lambda: _env_float("MAX_SPREAD_PCT", 0.60))

    # === الحجم والمخاطرة ===
    # ميزانية الصفقة الواحدة بالدولار
    trade_budget_usd: float = field(default_factory=lambda: _env_float("TRADE_BUDGET_USD", 25.0))
    # لا صفقة أقل من هذا المبلغ
    min_budget_usd: float = field(default_factory=lambda: _env_float("MIN_BUDGET_USD", 10.0))
    # أقصى خسارة مقبولة بالدولار في الصفقة الواحدة
    risk_per_trade_usd: float = field(default_factory=lambda: _env_float("RISK_PER_TRADE_USD", 1.0))
    max_open_positions: int = field(default_factory=lambda: _env_int("MAX_OPEN_POSITIONS", 2))
    # حد الخسارة اليومية (٪) الذي يفعّل الإيقاف الطارئ
    max_daily_loss_pct: float = field(default_factory=lambda: _env_float("MAX_DAILY_LOSS_PCT", 2.0))
    # أقصى عدد صفقات شراء في اليوم
    max_trades_per_day: int = field(default_factory=lambda: _env_int("MAX_TRADES_PER_DAY", 6))
    # فترة الانتظار بعد البيع قبل إعادة شراء نفس السهم (دقائق)
    symbol_cooldown_min: int = field(default_factory=lambda: _env_int("SYMBOL_COOLDOWN_MIN", 60))

    # === الخروج ===
    take_profit_pct: float = field(default_factory=lambda: _env_float("TAKE_PROFIT_PCT", 4.5))
    stop_loss_pct: float = field(default_factory=lambda: _env_float("STOP_LOSS_PCT", 2.5))
    # أوامر الشراء المعلّقة التي لم تُنفَّذ تُلغى بعد هذه المدة (ثوانٍ)
    entry_timeout_sec: int = field(default_factory=lambda: _env_int("ENTRY_TIMEOUT_SEC", 90))

    # === المحرك ===
    scan_interval_sec: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_SEC", 30))
    trade_extended_hours: bool = field(default_factory=lambda: _env_bool("TRADE_EXTENDED_HOURS", True))

    # === قاعدة البيانات ===
    # على Railway ضع: /data/bot_state.db (بعد إضافة Volume)
    db_path: str = field(default_factory=lambda: _env_str("DB_PATH", "bot_state.db"))

    # === تليجرام ===
    telegram_token: str = field(default_factory=lambda: _env_str("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env_str("TELEGRAM_CHAT_ID"))

    # === Webhook (TradingView) ===
    # لا قيمة افتراضية: بدونها يرفض البوت كل الأوامر
    webhook_passphrase: str = field(default_factory=lambda: _env_str("WEBHOOK_PASSPHRASE"))
    # Railway يحدّد PORT تلقائيًا
    port: int = field(default_factory=lambda: _env_int("PORT", 8080))

    def get_base_url(self) -> str:
        """رابط Alpaca حسب وضع التشغيل."""
        if self.paper:
            return "https://paper-api.alpaca.markets"
        return "https://api.alpaca.markets"


def validate_settings(s: "Settings" = None) -> List[str]:
    """يفحص الإعدادات ويرجع قائمة الأخطاء (فارغة = كل شيء سليم)."""
    s = s or settings
    errors: List[str] = []
    if not s.api_key:
        errors.append("ALPACA_API_KEY غير موجود في متغيرات البيئة")
    if not s.secret_key:
        errors.append("ALPACA_SECRET_KEY غير موجود في متغيرات البيئة")
    if not s.webhook_passphrase:
        errors.append("WEBHOOK_PASSPHRASE غير موجود — خادم Webhook سيكون معطّلاً")
    if s.data_feed not in ("iex", "sip"):
        errors.append(f"DATA_FEED يجب أن يكون iex أو sip (الحالي: {s.data_feed})")
    if s.min_price >= s.max_price:
        errors.append("MIN_PRICE يجب أن يكون أقل من MAX_PRICE")
    if s.stop_loss_pct <= 0 or s.take_profit_pct <= 0:
        errors.append("نسب وقف الخسارة وجني الربح يجب أن تكون أكبر من صفر")
    if s.max_spread_pct <= 0:
        errors.append("MAX_SPREAD_PCT يجب أن يكون أكبر من صفر")
    if not s.watchlist:
        errors.append("قائمة المراقبة WATCHLIST فارغة")
    if s.max_open_positions < 1:
        errors.append("MAX_OPEN_POSITIONS يجب أن يكون 1 أو أكثر")
    return errors


# نسخة واحدة تُستخدم في كل الملفات
settings = Settings()
