import os
import json
import sys
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# تحميل متغيرات البيئة
load_dotenv(override=False)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# مفتاح Zoya المباشر
ZOYA_API_KEY = "live-0267000b-e0d0-4ae0-9895-63dc1ec1d44a"

def send_telegram_msg(message_text):
    """إرسال رسالة بتنسيق HTML إلى تلغرام"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Warning] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML"
    }
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[Exception] Failed to send Telegram message: {e}")
        return False

def get_zoya_compliance(symbol):
    """فحص الفلترة الشرعية بإنعكاس ترويسات Authorization القياسية لـ Zoya"""
    if not ZOYA_API_KEY:
        return "المفتاح غير مدخل"
    
    # الترويسات المزدوجة لتفادي أخطاء الصلاحية (401)
    headers = {
        "X-API-KEY": ZOYA_API_KEY,
        "Authorization": f"Bearer {ZOYA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    query = """
    query GetCompliance($symbol: String!) {
      security(symbol: $symbol) {
        ticker
        compliance {
          status
          isCompliant
        }
      }
    }
    """
    
    payload = {
        "query": query,
        "variables": {"symbol": str(symbol).upper()}
    }
    
    endpoints = [
        "https://api.zoya.finance/graphql",
        "https://sandbox.zoya.finance/graphql"
    ]
    
    for url in endpoints:
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                sec = data.get("data", {}).get("security")
                if sec and "compliance" in sec:
                    return sec.get("compliance")
        except Exception:
            continue
            
    return "خطأ صلاحية (401)"

def process_alert_data(data, raw_data=""):
    """معالجة التنبيه وبناء النص وإرساله إلى تلغرام"""
    raw_symbol = str(data.get('symbol', '') or data.get('ticker', '') or '').strip().upper()
    
    if ":" in raw_symbol:
        symbol = raw_symbol.split(":")[-1]
    else:
        symbol = raw_symbol

    price = str(data.get("price", "N/A")).strip()
    action = str(data.get("action", "ALERT")).strip().upper()
    reason = str(data.get("reason", "تنبيه فني")).strip()
    interval = str(data.get("interval", "غير محدد")).strip()
    volume = str(data.get("volume", "N/A")).strip()

    if not symbol:
        symbol = "تنبيه عام"
        reason = raw_data if raw_data else "تنبيه بدون بيانات"

    shariah_text = "فحص الشرعية غير متاح"

    if symbol != "تنبيه عام":
        zoya_res = get_zoya_compliance(symbol)
        
        if isinstance(zoya_res, dict):
            status = str(zoya_res.get("status", "مفحوص")).upper()
            is_compliant = zoya_res.get("isCompliant")

            if is_compliant is True or status == "COMPLIANT":
                shariah_text = f"✅ متوافق شرعاً ({status})"
            elif is_compliant is False or status == "NON_COMPLIANT":
                shariah_text = f"❌ غير متوافق شرعاً ({status})"
            else:
                shariah_text = f"ℹ️ حالة التوافق: {status}"
        elif zoya_res is None:
            shariah_text = "لم يتم العثور على بيانات شرعية"
        else:
            shariah_text = f"⚠️ {zoya_res}"

    action_emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "🔵"

    message_text = (
        f"{action_emoji} <b>تنبيه فرصة تداول ({symbol})</b>\n\n"
        f"📌 <b>السهم:</b> <code>{symbol}</code>\n"
        f"💰 <b>السعر الحالي:</b> ${price}\n"
        f"🎯 <b>نوع الإشارة:</b> {action}\n"
        f"⏱ <b>الفاصل الزمني:</b> {interval}\n"
        f"📊 <b>حجم التداول:</b> {volume}\n"
        f"📝 <b>السبب:</b> {reason}\n\n"
        f"🕋 <b>الوضع الشرعي (Zoya):</b>\n{shariah_text}"
    )

    return send_telegram_msg(message_text)

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw_data = request.get_data(as_text=True)
        data = {}
        try:
            data = json.loads(raw_data)
        except Exception:
            data = request.get_json(force=True, silent=True) or {}
            
        success = process_alert_data(data, raw_data)
        if success:
            return jsonify({"status": "success", "message": "Alert sent to Telegram"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to send to Telegram"}), 500
    except Exception as err:
        return jsonify({"status": "error", "message": str(err)}), 500

if __name__ == "__main__":
    if os.getenv("GITHUB_ACTIONS") == "true":
        print("[INFO] Running in GitHub Actions CLI mode...")
        test_payload = {
            "symbol": "TSLA",
            "action": "CHECK",
            "price": "N/A",
            "reason": "فحص مجدول من GitHub Actions",
            "interval": "Scheduled",
            "volume": "N/A"
        }
        status = process_alert_data(test_payload)
        if status:
            print("[SUCCESS] GitHub Action run completed successfully.")
            sys.exit(0)
        else:
            print("[FAILURE] Failed to process action.")
            sys.exit(1)
    else:
        app.run(host="0.0.0.0", port=5000)
