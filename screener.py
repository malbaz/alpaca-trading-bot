import os
import time
import requests
import yfinance as yf

# ---------------------------------------------------------
# 1. الإعدادات وقائمة الأسهم المحدثة (مطابقة لبوت التداول)
# ---------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# القائمة الشاملة للأسهم المميزة والشرعية ذات الزخم المرتفع
WATCHLIST = [
    # الأسهم النارية المضافة حديثاً
    "EEIQ", "HSCS", "CVM", "EFOI", "CSAI", "LONA", "AZ", "JDZG", 
    "RTB", "LNZA", "MTNB", "IDAI", "AIRG", "BMHL", "PICS", "RGC", 
    "HYLN", "FISN", "CJMB", "BTLN", "INTS", "DFNS", "OSG", "EP", 
    "CTNT", "DDD", "RXT", "SOC", "CUVL", "SOTK", "KOPN", "SHIM",
    # أسهم الزخم المتميزة
    "OPTX", "INDP", "ATRA", "MYGN", "NFE", "ABLV", "GRDX", "WVVI",
    "AMOD", "SDEV", "AIXI", "ZNB", "CYCU", "GOW", "PMI", "NNBR", 
    "NAUT", "ICU", "REBN", "NEOV", "FEAM", "SSM", "IMC", "CELU",
    # الأسهم الشرعية النشطة
    "ONCY", "ABVC", "TLSI", "DBRG", "AMIX", "DAIC", "VEEA", 
    "FTFT", "SOUN", "BBAI", "LUNR", "SERV", "BZFD", "QNST", 
    "SHIP", "CWCO", "BNAI", "AISP", "KULR", "RIG", "GTEC", 
    "PDSB", "GRML", "BFLY", "EAF", "IPDN", "WFCF"
]

# معايير التصفية واقتناص الاختراقات
MIN_PRICE = 1.50               # الحد الأدنى لسعر السهم لتجنب الانزلاق السعري
MAX_PRICE = 16.00              # الحد الأقصى لسعر السهم
MIN_MOMENTUM_PCT = 3.5         # نسبة الاختراق اللحظي المطلوبة (3.5%+)
MIN_VOLUME = 200000            # حد السيولة وحجم التداول (200 ألف+)

# نسب التوصية للتحليل والاستهداف
QUICK_TAKE_PROFIT_PCT = 0.045  # +4.5%
MAX_TAKE_PROFIT_PCT = 0.080    # +8.0%
STOP_LOSS_PCT = 0.035          # -3.5%

# ---------------------------------------------------------
# 2. دالة إرسال التنبيه المنسق إلى التليجرام
# ---------------------------------------------------------

def escape_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_alert(symbol, price, change_percent, volume, is_extended=True):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("خطأ: إعدادات التليجرام غير مضافة بشكل صحيح.")
        return False

    target_fast = round(price * (1 + QUICK_TAKE_PROFIT_PCT), 2)
    target_max = round(price * (1 + MAX_TAKE_PROFIT_PCT), 2)
    stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
    
    market_phase = "تداول ممتد (Pre/After-Market) 🌙" if is_extended else "الجلسة الرسمية ☀️"

    message_text = (
        f"🔍 <b>تنبيه ماسح السوق (Market Scanner)</b>\n"
        f"({market_phase})\n\n"
        f"📌 <b>رمز السهم:</b> <code>{escape_html(symbol)}</code>\n"
        f"🔥 <b>حالة الفرصة:</b> اختراق لحظي وزخم صاعد\n"
        f"🎯 <b>سعر الرصد الحالي:</b> ${price:.2f}\n\n"
        f"📊 <b>الزخم اللحظي (5 دقائق):</b> +{change_percent:.2f}%\n"
        f"⚡ <b>حجم السيولة والنشاط:</b> {volume:,}\n\n"
        f"🚀 <b>هدف الخروج الخاطف (+{QUICK_TAKE_PROFIT_PCT*100:.1f}%):</b>\n${target_fast:.2f}\n\n"
        f"🏆 <b>الهدف الممتد (+{MAX_TAKE_PROFIT_PCT*100:.1f}%):</b> ${target_max:.2f}\n\n"
        f"🚨 <b>وقف الخسارة المقترح (-{STOP_LOSS_PCT*100:.1f}%):</b>\n${stop_loss:.2f}\n"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message_text, 
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"خطأ أثناء إرسال تنبيه الماسح: {e}")
        return False

# ---------------------------------------------------------
# 3. المحرك الرئيسي للماسح
# ---------------------------------------------------------

def run_market_scanner():
    print("بدء تشغيل ماسح السوق ومراقبة الفرص النارية...")
    found_opportunities = 0

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            # جلب البيانات اللحظية لدقيقة واحدة متضمنة الفترات الممتدة
            df = ticker.history(period="1d", interval="1m", prepost=True)

            if df.empty or len(df) < 10:
                continue

            current_price = float(df['Close'].iloc[-1])
            price_5m_ago = float(df['Close'].iloc[-5])
            volume_sum = int(df['Volume'].iloc[-10:].sum())

            # 1. التصفية بناءً على السعر المعتمد
            if not (MIN_PRICE <= current_price <= MAX_PRICE):
                continue

            # 2. حساب الزخم الصاعد لآخر 5 دقائق
            instant_momentum_pct = ((current_price - price_5m_ago) / price_5m_ago) * 100

            # 3. التحقق من تحقق الشروط وإرسال التنبيه
            if instant_momentum_pct >= MIN_MOMENTUM_PCT and volume_sum >= MIN_VOLUME:
                print(f"🎯 تم رصد فرصة ممتازة على {symbol}: +{instant_momentum_pct:.2f}% | السيولة: {volume_sum:,}")
                
                success = send_telegram_alert(symbol, current_price, instant_momentum_pct, volume_sum, is_extended=True)
                if success:
                    print(f"✅ تم إرسال تنبيه {symbol} إلى التليجرام بنجاح.")
                    found_opportunities += 1

        except Exception as e:
            print(f"خطأ أثناء مسح السهم {symbol}: {e}")

    if found_opportunities == 0:
        print("اكتمل المسح: لا توجد اختراقات لحظية مطابقة للشروط في هذه الدورة.")
    else:
        print(f"اكتمل المسح: تم رصد وإرسال {found_opportunities} فرصة.")

if __name__ == "__main__":
    run_market_scanner()
