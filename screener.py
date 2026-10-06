import os
import requests
import yfinance as yf
from order_manager import order_manager
from risk_engine import risk_engine

WATCHLIST = [
    # الأسهم المضافة حديثاً
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

def run_screener():
    print("🔍 بدء مسح الفلاتر المتقدمة المربوطة بـ OrderManager...")
    
    # 1. مطابقة مراكز Alpaca أولاً مع ذاكرة البوت
    order_manager.reconcile_positions()

    for symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="1m", prepost=True)
            if df.empty or len(df) < 10:
                continue

            current_price = float(df['Close'].iloc[-1])
            price_5m_ago = float(df['Close'].iloc[-5])
            volume_sum = int(df['Volume'].iloc[-10:].sum())

            # الفلترة الأساسية السعرية
            if not (1.50 <= current_price <= 16.00):
                continue

            momentum_pct = ((current_price - price_5m_ago) / price_5m_ago) * 100

            # شرط الزخم (+3.5%) والحجم (300K+)
            if momentum_pct >= 3.5 and volume_sum >= 300000:
                print(f"🔥 فرصة مكتشفة بواسطة Screener: {symbol} (+{momentum_pct:.2f}%)")
                
                bid = current_price * 0.999
                ask = current_price * 1.001

                # فحص المخاطر أولاً عبر RiskEngine
                if risk_engine.is_trade_allowed(symbol, bid, ask):
                    result = order_manager.process_buy_signal(symbol, current_price, budget=50.0)
                    print(f"نتيجة التنفيذ الموحد لـ {symbol}: {result}")

        except Exception as e:
            print(f"خطأ فحص السهم {symbol}: {e}")

if __name__ == "__main__":
    run_screener()
