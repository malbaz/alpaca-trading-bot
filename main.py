import os
import json
import sys
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv(override=False)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ZOYA_API_KEY = os.getenv("ZOYA_API_KEY", "").strip()

def send_telegram_msg(message_text):
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
    """جلب الشرعية عبر استعلام Zoya API الرسمي المعتمد"""
    if not ZOYA_API_KEY:
        return "لم يتم تعيين ZOYA_API_KEY في Secrets"
    
    url = "https://sandbox.zoya.finance/graphql" if ZOYA_API_KEY.startswith("sandbox-") else "https://api.zoya.finance/graphql"

    headers = {
        "Authorization": f"Bearer {ZOYA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # الاستعلام الرسمي المعتمد في Zoya GraphQL Reference
    query = """
    query GetCompliance($symbol: String!) {
      security(symbol: $symbol) {
        symbol
        name
        shariahCompliance {
          status
          isCompliant
          report {
            nonPermissibleRevenuePercentage
            totalDebtToMarketCapPercentage
          }
        }
      }
    }
    """
    
    payload = {
        "query": query,
        "variables": {"symbol": str(symbol).upper()}
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            sec = data.get("data", {}).get("security")
            if sec and "shariahCompliance" in sec:
                return sec.get("shariahCompliance")
            
            # خطة محاولة ثانية باسم الحقن المتوافق (enrichments)
            query_alt = """
            query GetComplianceAlt($symbol: String!) {
              security(symbol: $symbol) {
                compliance {
                  status
                  isCompliant
                }
              }
            }
            """
            res_alt = requests.post(url, json={"query": query_alt, "variables": {"symbol": str(symbol).upper()}}, headers=headers, timeout=5)
            if res_alt.status_code == 200:
                sec_alt = res_alt.json().get("data", {}).get("security")
                if sec_alt and "compliance" in sec_alt:
                    return sec_alt.get("compliance")

        elif res.status_code == 401:
            return "مفتاح API غير صالح أو ملغى (401)"
    except Exception as e:
        print(f"[Exception] Zoya Query Error: {e}")
            
    return "بيانات غير متاحة"

def process_alert_data(data, raw_data=""):
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
            report = zoya_res.get("report") or {}
            debt = float(report.get("totalDebtToMarketCapPercentage") or 0.0)
            rev = float(report.get("nonPermissibleRevenuePercentage") or 0.0)

            if is_compliant is True or status == "COMPLIANT":
                shariah_text = f"✅ متوافق شرعاً ({status})"
                if debt > 0 or rev > 0:
                    shariah_text += f"\n   الديون: {debt:.2f}%\n   غير المباح: {rev:.2f}%"
            elif is_compliant is False or status == "NON_COMPLIANT":
                shariah_text = f"❌ غير متوافق شرعاً ({status})"
                if debt > 0 or rev > 0:
                    shariah_text += f"\n   الديون: {debt:.2f}%\n   غير المباح: {rev:.2f}%"
            else:
                shariah_text = f"ℹ️ حالة التوافق: {status}"
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
