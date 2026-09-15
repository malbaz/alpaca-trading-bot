import os
import requests
import yfinance as yf

# استدعاء متغيرات البيئة الخاصة بتليجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# قائمة استرشادية لأسهم السمول كاب للمسح
WATCHLIST = [
    "AMIX", "ADXN", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV", 
    "MARK", "CYN", "MULN", "PLTR", "SASI", "BZFD", "NVVE", "JEM"
]

def send_telegram_alert(symbol, name, price, volume, change_percent):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("خطأ: مفاتيح تليجرام غير مضافة في البيئة.")
        return

    # احتساب الأهداف ووقف الخسارة بناءً على السعر الحالي
    entry_price = round(price, 2)
    tp1 = round(entry_price * 1.10, 2)  # هدف أول +10%
    tp2 = round(entry_price * 1.25, 2)  # هدف ثانٍ +25%
    sl = round(entry_price * 0.93, 2)   # وقف خسارة -7%

    message_text = (
        f"<b>🟢 فرصة تداول مكتشفة تلقائياً</b>\n\n"
        f"📌 <b>رمز واسم السهم:</b> <code>{symbol}</code> ({name})\n"
        f"⚡ <b>اتجاه الصفقة:</b> شراء (اختراق وزخم)\n"
        f"⏱️ <b>الإطار الزمني:</b> لحظي / يومي\n"
        f"💰 <b>نطاق سعر ووقت الدخول:</b> ${entry_price} | مسح آلي\n\n"
        f"📊 <b>التغير اليومي:</b> +{change_percent:.2f}%\n"
        f"📈 <b>حجم التداول:</b> {volume:,}\n\n"
        f"🎯 <b>الهدف الأول:</b> ${tp1}\n"
        f"🎯 <b>الهدف الثاني:</b> ${tp2}\n"
        f"🎯 <b>الهدف الثالث:</b> غير محدد\n\n"
        f"🛑 <b>سعر وقف الخسارة:</b> ${sl}\n"
        f"⏳ <b>وقت الخروج المقترح:</b> عند تحقق الهدف أو كسر وقف الخسارة"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML"
    }

    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            print(f"تم إرسال تنبيه السهم {symbol} بنجاح.")
    except Exception as e:
        print(f"فشل إرسال التنبيه للسهم {symbol}: {e}")

def run_screener():
    print("بدء عملية مسح السوق...")
    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            
            if len(hist) < 2:
                continue

            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2]
            volume = hist['Volume'].iloc[-1]
            change_percent = ((current_price - prev_price) / prev_price) * 100

            # شروط جودة الفرصة: السعر (1$-15$)، ارتفاع > 3%، حجم تداول > 300,000
            if 1.0 <= current_price <= 15.0 and change_percent >= 3.0 and volume >= 300000:
                short_name = stock.info.get('shortName', ticker)
                send_telegram_alert(ticker, short_name, current_price, volume, change_percent)

        except Exception as e:
            print(f"خطأ أثناء فحص السهم {ticker}: {e}")

if __name__ == "__main__":
    run_screener()
