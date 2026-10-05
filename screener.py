import os
import yfinance as yf

# ---------------------------------------------------------
# 1. قائمة الأسهم المحدثة الموحدة
# ---------------------------------------------------------

# القائمة الشاملة الموحدة المطابقة لبوت التداول
WATCHLIST = [
    # الأسهم المضافة حديثاً من الشاشات
    "BOOM", "BRBR", "BNED", "BOF", "BLZE", "BKKT", "BIAF", "AXIL", 
    "AYTU", "AVO", "AVPT",
    # الأسهم المميزة المعتمدة سابقاً
    "AMOD", "NSTR", "AIXI", "CYCU", "PMI", "AMPL", "AMPX", "ABSI", 
    "AMBO", "AEYE", "AIOT", "AENT", "ADTN", "ABEO", "ABTE", "ZNB",
    "EEIQ", "HSCS", "CVM", "EFOI", "CSAI", "LONA", "AZ", "JDZG", 
    "RTB", "LNZA", "MTNB", "IDAI", "AIRG", "BMHL", "PICS", "RGC", 
    "HYLN", "FISN", "CJMB", "BTLN", "INTS", "DFNS", "OSG", "EP", 
    "CTNT", "DDD", "RXT", "SOC", "CUVL", "SOTK", "KOPN", "SHIM",
    "OPTX", "INDP", "ATRA", "MYGN", "NFE", "ABLV", "GRDX", "WVVI",
    "SDEV", "GOW", "NNBR", "NAUT", "ICU", "REBN", "NEOV", "FEAM", 
    "SSM", "IMC", "CELU", "ONCY", "ABVC", "TLSI", "DBRG", "AMIX", 
    "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", "LUNR", "SERV", "BZFD", 
    "QNST", "SHIP", "CWCO", "BNAI", "AISP", "KULR", "RIG", "GTEC", 
    "PDSB", "GRML", "BFLY", "EAF", "IPDN", "WFCF"
]

# معايير التصفية واقتناص الاختراقات
MIN_PRICE = 1.50               # الحد الأدنى لسعر السهم
MAX_PRICE = 16.00              # الحد الأقصى لسعر السهم
MIN_MOMENTUM_PCT = 3.5         # نسبة الاختراق اللحظي المطلوبة (+3.5%)
MIN_VOLUME = 200000            # حد السيولة وحجم التداول

# ---------------------------------------------------------
# 2. المحرك الرئيسي للماسح الصامت (بدون إرسال رسائل تليجرام)
# ---------------------------------------------------------

def run_market_scanner():
    print("بدء تشغيل ماسح السوق الصامت (فحص وحفظ سجلات بدون تنبيهات تليجرام)...")
    found_opportunities = 0

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="1m", prepost=True)

            if df.empty or len(df) < 10:
                continue

            current_price = float(df['Close'].iloc[-1])
            price_5m_ago = float(df['Close'].iloc[-5])
            volume_sum = int(df['Volume'].iloc[-10:].sum())

            # 1. التصفية السعرية
            if not (MIN_PRICE <= current_price <= MAX_PRICE):
                continue

            # 2. حساب الزخم اللحظي لآخر 5 دقائق
            instant_momentum_pct = ((current_price - price_5m_ago) / price_5m_ago) * 100

            # 3. طباعة الفرص في سجلات GitHub فقط بدون إرسال للتليجرام
            if instant_momentum_pct >= MIN_MOMENTUM_PCT and volume_sum >= MIN_VOLUME:
                found_opportunities += 1
                print(f"🔍 [مسح صامت] فرصة مرصودة على {symbol}: سعر ${current_price:.2f} | زخم +{instant_momentum_pct:.2f}% | سيولة: {volume_sum:,}")

        except Exception as e:
            print(f"خطأ أثناء مسح السهم {symbol}: {e}")

    if found_opportunities == 0:
        print("اكتمل المسح الصامت: لا توجد فرص جديدة مطابقة للشروط.")
    else:
        print(f"اكتمل المسح الصامت: تم رصد {found_opportunities} فرصة في السجلات.")

if __name__ == "__main__":
    run_market_scanner()
