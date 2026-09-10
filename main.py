import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest

load_dotenv(override=True)

app = Flask(__name__)

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

# ذاكرة مؤقتة لمنع تكرار التنبيهات لنفس السهم
LAST_ALERT_TIME = {}
ALERT_COOLDOWN_SECONDS = 14400  # حظر التكرار لمدة 4 ساعات لكل سهم

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
    """معالجة وتصفية التنبيهات لتقليل الرسائل وحصرها على الفرص الشرعية والقوية"""
    symbol = data.get("symbol", "").upper()
    price = data.get("price", "N/A")
    action = data.get("action", "ALERT")
    reason = data.get("reason", "تنبيه تلقائي")
    rsi = data.get("rsi")

    if not symbol:
        return {"status": "error", "message": "Symbol missing"}

    # 1. منع التكرار والتردد لنفس السهم خلال 4 ساعات
    current_time = time.time()
    if symbol in LAST_ALERT_TIME:
        elapsed = current_time - LAST_ALERT_TIME[symbol]
        if elapsed < ALERT_COOLDOWN_SECONDS:
            print(f"Ignored {symbol}: Cooldown active ({int(elapsed)}s remaining)")
            return {"status": "ignored", "reason": "Alert rate limited"}

    # 2. التصفية الشرعية الصارمة عبر Zoya API
    zoya_data = get_zoya_compliance(symbol)
    if zoya_data:
        is_compliant = zoya_data.get("isCompliant", False)
        status = zoya_data.get("status", "UNKNOWN")
        
        # حجب السهم إذا لم يكن متوافقاً 100%
        if not is_compliant or status != "COMPLIANT":
            print(f"Ignored {symbol}: Non-compliant or questionable status ({status})")
            return {"status": "ignored", "reason": f"Non-compliant stock ({status})"}
            
        report = zoya_data.get("report", {})
        debt_ratio = report.get("debtToMarketCapPercentage", 0) or 0
        revenue_ratio = report.get("nonPermissibleRevenuePercentage", 0) or 0
        interest_assets = report.get("interestBearingAssetsPercentage", 0) or 0
    else:
        # حجب السهم إذا تعذر التحقق الشرعي تقليلاً للرسائل غير المضمونة
        print(f"Ignored {symbol}: Could not verify Shariah compliance")
        return {"status": "ignored", "reason": "Shariah status unverified"}

    # 3. تصفية الفرص الضعيفة فندياً (فحص مؤشر RSI إن وجد في التنبيه)
    if rsi is not None:
        try:
            rsi_val = float(rsi)
            if action == "BUY" and rsi_val > 40:
                print(f"Ignored {symbol}: Weak RSI ({rsi_val})")
                return {"status": "ignored", "reason": "RSI too high for strong buy"}
        except ValueError:
            pass

    # تحديث وقت آخر تنبيه للسهم
    LAST_ALERT_TIME[symbol] = current_time

    # 4. صياغة التقرير للفرص المعتمدة العالية الاحتمالية فقط
    shariah_section = f"""
---
🕌 **تقرير الفحص الشرعي (Zoya API - AAOIFI):**
✅ **الحالة الشرعية:** {status}
📊 **نسبة الديون/القيمة السوقية:** `{debt_ratio:.2f}%` (الحد 30%)
💰 **الإيرادات غير الحرّة:** `{revenue_ratio:.2f}%` (الحد 5%)
🏦 **الأصول الربوية:** `{interest_assets:.2f}%` (الحد 30%)"""

    msg = f"""🔥 **فرصة شرعية عالية الاحتمالية**

🏷️ **السهم:** `{symbol}`
💵 **السعر الحالي:** `${price}`
🎯 **الإجراء:** `{action}`
📌 **السبب:** {reason}
{shariah_section}"""

    send_telegram_msg(msg)
    return {"status": "success"}

def check_portfolio_compliance():
    """فحص دوري لجميع الأسهم المملوكة في المحفظة وإرسال تحذير على تيليجرام عند تغير الحالة"""
    if not MANUAL_POSITIONS:
        return {"status": "success", "message": "المحفظة فارغة"}

    alerts = []
    
    for symbol in MANUAL_POSITIONS.keys():
        zoya_data = get_zoya_compliance(symbol)
        if zoya_data:
            is_compliant = zoya_data.get("isCompliant", False)
            status = zoya_data.get("status", "UNKNOWN")
            
            if not is_compliant or status != "COMPLIANT":
                report = zoya_data.get("report", {})
                debt_ratio = report.get("debtToMarketCapPercentage", 0) or 0
                revenue_ratio = report.get("nonPermissibleRevenuePercentage", 0) or 0
                
                alert_msg = f"""⚠️ **تنبيه طارئ: تغير الحالة الشرعية لسهم مملوك!**

🏷️ **السهم:** `{symbol}`
📊 **الحالة الجديدة:** `{status}`
📉 **تفاصيل النسب:**
  • نسبة الديون: `{debt_ratio:.2f}%`
  • الإيرادات غير الحرّة: `{revenue_ratio:.2f}%`

‼️ **توصية:** يرجى مراجعة وضع السهم لاتخاذ قرار التصفية أو الخروج.
"""
                send_telegram_msg(alert_msg)
                alerts.append(symbol)

    if alerts:
        return {"status": "warning", "non_compliant_stocks": alerts}
    return {"status": "success", "message": "جميع أسهم المحفظة متوافقة شرعياً"}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json or {}
    res = process_webhook_alert(data)
    return jsonify(res), 200

@app.route('/check-compliance', methods=['GET', 'POST'])
def run_compliance_check():
    result = check_portfolio_compliance()
    return jsonify(result), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
