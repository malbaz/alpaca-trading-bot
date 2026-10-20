"""إرسال توصيات الدخول إلى مجموعة العملاء — معزول تمامًا عن التداول.

أي خطأ هنا لا يوقف البوت ولا يؤثر على تنفيذ الصفقات.
"""

import logging
import os

import requests

log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SIGNALS_CHAT_ID = os.getenv("TELEGRAM_SIGNALS_CHAT_ID", "")


def send_signal(symbol: str, entry: float, stop: float, target: float) -> None:
    """يرسل توصية دخول منسّقة إلى مجموعة العملاء. لا يرمي أي استثناء أبدًا."""
    if not BOT_TOKEN or not SIGNALS_CHAT_ID:
        return
    try:
        text = (
            "📈 <b>توصية دخول — تحليل فرصة</b>\n\n"
            f"السهم: <b>{symbol}</b>\n"
            f"سعر الدخول: <b>{entry:.2f}$</b>\n"
            f"🎯 الهدف: <b>{target:.2f}$</b>\n"
            f"🛑 وقف الخسارة: <b>{stop:.2f}$</b>\n\n"
            "⚠️ إخلاء مسؤولية: التنبيهات لا تضمن الربح وليست مضمونة 100%. "
            "التداول في السوق يقع تحت مسؤوليتك الشخصية وقرارك."
        )
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": SIGNALS_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — العزل مقصود
        log.warning("signals: فشل إرسال التوصية (%s) — التداول مستمر طبيعيًا", exc)
