"""إرسال التنبيهات إلى تليجرام (HTML مع تهريب النصوص)."""
import html
import logging
import requests

from config import settings

log = logging.getLogger("alerts")


def send(text: str) -> bool:
    if not settings.telegram_token or not settings.telegram_chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=8,
        )
        if r.status_code != 200:
            log.warning("Telegram error %s: %s", r.status_code, r.text[:200])
        return r.status_code == 200
    except Exception as e:  # الشبكة لا يجب أن توقف التداول
        log.warning("Telegram exception: %s", e)
        return False


def esc(v) -> str:
    return html.escape(str(v))


def entry_filled(symbol, qty, price, target, stop, mode):
    send(
        f"🟢 <b>تم تنفيذ شراء</b> ({esc(mode)})\n\n"
        f"📌 <b>السهم:</b> <code>{esc(symbol)}</code>\n"
        f"🔢 <b>الكمية:</b> {qty}\n"
        f"💰 <b>سعر التنفيذ:</b> ${price:.2f}\n"
        f"🎯 <b>الهدف:</b> ${target:.2f}\n"
        f"🛑 <b>وقف الخسارة:</b> ${stop:.2f}"
    )


def exit_filled(symbol, qty, entry, exit_price, reason):
    pnl = (exit_price - entry) * qty if entry else 0
    icon = "✅" if pnl >= 0 else "🔻"
    send(
        f"{icon} <b>تم إغلاق المركز</b>\n\n"
        f"📌 <b>السهم:</b> <code>{esc(symbol)}</code>\n"
        f"💰 <b>الدخول/الخروج:</b> ${entry:.2f} ← ${exit_price:.2f}\n"
        f"📊 <b>النتيجة:</b> ${pnl:+.2f}\n"
        f"📝 <b>السبب:</b> {esc(reason)}"
    )


def system(msg: str):
    send(f"⚙️ <b>النظام:</b> {esc(msg)}")
