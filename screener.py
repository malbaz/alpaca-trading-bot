import os
import requests
import yfinance as yf
from datetime import datetime
from order_manager import order_manager
from risk_engine import risk_engine

WATCHLIST = [
    "BOOM", "BRBR", "BNED", "BOF", "BLZE", "BKKT", "BIAF", "AXIL", 
    "AYTU", "AVO", "AVPT", "AMOD", "NSTR", "AIXI", "CYCU", "PMI", 
    "AMPL", "AMPX", "ABSI", "AMBO", "AEYE", "AIOT", "AENT", "ADTN", 
    "ABEO", "ABTE", "ZNB", "EEIQ", "HSCS", "CVM", "EFOI", "CSAI", 
    "LONA", "AZ", "JDZG", "RTB", "LNZA", "MTNB", "IDAI", "AIRG", 
    "BMHL", "PICS", "RGC", "HYLN", "FISN", "CJMB", "BTLN", "INTS", 
    "DFNS", "OSG", "EP", "CTNT", "DDD", "RXT", "SOC", "CUVL", 
    "SOTK", "KOPN", "SHIM", "OPTX", "INDP", "ATRA", "MYGN", "NFE", 
    "ABLV", "GRDX", "WVVI", "SDEV", "GOW", "NNBR", "NAUT", "ICU", 
    "REBN", "NEOV", "FEAM", "SSM", "IMC", "CELU", "ONCY", "ABVC", 
    "TLSI", "DBRG", "AMIX", "DAIC", "VEEA", "FTFT", "SOUN", "BBAI", 
    "LUNR", "SERV", "BZFD", "QNST", "SHIP", "CWCO", "BNAI", "AISP", 
    "KULR", "RIG", "GTEC", "PDSB", "GRML", "BFLY", "EAF", "IPDN", "WFCF"
]

def run_screener():
    print("🔍 بدء مسح الفلاتر المتقدمة (يشمل فترات Pre-Market و After-Hours)...")
    
    order_manager.reconcile_positions()

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            # prepost=True لتغطية الفترات الممتدة
            df = ticker.history(period="1d", interval="1m", prepost=True)
            if df.empty or len(df) < 5:
                continue

            current_price = float(df['Close'].iloc[-1])
            price_5m_ago = float(df['Close'].iloc[-min(5, len(df))])
            volume_sum = int(df['Volume'].iloc[-10:].sum())

            # التعديل للسماح بأسهم تبدأ من 1.00 دولار
if not (1.00 <= current_price <= 16.00):
    continue

            momentum_pct = ((current_price - price_5m_ago) / price_5m_ago) * 100

            # مرونة حجم التداول خلال الفترات الممتدة (50K سهم كافي خارج الأوقات الرسمية)
            min_volume = 50000 

            if momentum_pct >= 3.0 and volume_sum >= min_volume:
                print(f"🔥 فرصة مكتشفة: {symbol} (+{momentum_pct:.2f}%) | الحجم: {volume_sum}")
                
                bid = current_price * 0.995
                ask = current_price * 1.005

                if risk_engine.is_trade_allowed(symbol, bid, ask):
                    result = order_manager.process_buy_signal(symbol, current_price, budget=50.0)
                    print(f"نتيجة التنفيذ لـ {symbol}: {result}")

        except Exception as e:
            print(f"خطأ فحص السهم {symbol}: {e}")

if __name__ == "__main__":
    run_screener()
