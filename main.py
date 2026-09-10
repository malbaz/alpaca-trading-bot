import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest

load_dotenv(override=True)

# المتغيرات الأساسية للمشروع
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip().strip('"')
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# متغيرات Zoya API
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()
ZOYA_GRAPHQL_URL = "https://api.zoya.finance/graphql"

trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

# بيانات الأسهم المملوكة على (عوائد / سهم)
MANUAL_POSITIONS = {
    "AMIX": {"qty": 427, "avg_price": 13.86},
    "ADXN": {"qty": 863, "avg_price": 8.85}
}

def send_telegram_msg(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_zoya_compliance(symbol):
    """جلب حالة الشرعية والنسب المالية من Zoya API"""
    if not ZOYA_API_KEY:
        print("Warning: ZOYA_API_KEY is not set.")
        return None
        
    headers = {
        "Authorization": f"Bearer {ZOYA_API_KEY}",
        "Content-Type": "application/json"
    }
    query = """
    query GetCompliance($symbol: String!) {
      security(symbol: $symbol) {
        symbol
        name
        compliance {
          status
          isCompliant
          report {
            nonPermissibleRevenuePercentage
            debtToMarketCapPercentage
            interestBearingAssetsPercentage
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {"symbol": symbol.upper()}
    }
    try:
        res = requests.post(ZOYA_GRAPHQL_URL, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "errors" in data:
                print(f"Zoya GraphQL Error: {data['errors']}")
                return None
            return data.get("data", {}).get("security", {}).get("compliance", {})
        else:
            print(f"Zoya API HTTP Error: {res.status_code}")
    except Exception as e:
        print(f"Error connecting to Zoya API: {e}")
    return None

def process_webhook_alert(data):
    """معالجة التنبيه الوارد وتطبيق الفحص الشرعي قبل الإرسال"""
    symbol = data.get("symbol", "").upper()
    price = data.get("price", "N/A")
    action = data.get("action", "ALERT")
    reason = data.get("reason", "تنبيه تلقائي من TradingView")

    if not symbol:
        return {"status": "error", "message": "Symbol missing"}

    # 1. التصفية والتأكد من الشرعية عبر Zoya
    zoya_data = get_zoya_compliance(symbol)
    
    if zoya_data:
        is_compliant = zoya_data.get("isCompliant", False)
        status = zoya_data.get("status", "UNKNOWN")
        
        # حجب السهم إذا كان غير متوافق شرعياً
        if not is_compliant:
            print(f"Ignored alert for {symbol}: Non-compliant status ({status})")
            return {"status": "ignored", "reason": f"Non-compliant stock ({status})"}
            
        report = zoya_data.get("report", {})
        debt_ratio = report.get("debtToMarketCapPercentage", 0) or 0
        revenue_ratio = report.get("nonPermissibleRevenuePercentage", 0) or 0
        interest_assets = report.get("interestBearingAssetsPercentage", 0) or 0
        
        shariah_section = f"""
---
🕌 **تقرير الفحص الشرعي (Zoya API - AAOIFI):**
✅ **الحالة الشرعية:** {status}
📊 **نسبة الديون/القيمة السوقية:** `{debt_ratio:.2f}%` (الحد 30%)
💰 **الإيرادات غير الحرّة:** `{revenue_ratio:.2f}%` (الحد 5%)
🏦 **الأصول الربوية:** `{interest_assets:.2f}%` (الحد 30%)"""
    else:
        shariah_section = "\n---\n🕌 **تقرير الفحص الشرعي:** تعذر جلب البيانات من Zoya"

    # 2. صياغة وتنسيق التقرير النهائي لتيليجرام
    msg = f"""🚨 **تنبيه تداول جديد - تحليل فرصة**

🏷️ **السهم:** `{symbol}`
💵 **السعر الحالي:** `${price}`
🎯 **الإجراء:** `{action}`
📌 **السبب:** {reason}
{shariah_section}"""

    send_telegram_msg(msg)
    return {"status": "success"}
