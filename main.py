import multiprocessing
import os
import sys
from webhook_server import app
from data_stream import start_stream

def run_stream():
    """تشغيل بث الأسعار اللحظي عبر Alpaca SIP في عملية مستقلة"""
    try:
        print("⚡ [Process] جاري بدء تشغيل عملية بث بيانات SIP...")
        start_stream()
    except Exception as e:
        print(f"❌ [Error] حدث خطأ أثناء تشغيل بث البيانات: {e}", file=sys.stderr)

if __name__ == "__main__":
    # 1. تشغيل بث الأسعار اللحظي (data_stream.py) في عملية منفصلة
    stream_process = multiprocessing.Process(target=run_stream, daemon=True)
    stream_process.start()

    # 2. جلب المنفذ المخصص من متغيرات البيئة (Railway يوفر PORT تلقائياً)
    port = int(os.getenv("PORT", 5000))
    
    # 3. تشغيل سيرفر استقبال التنبيهات (Webhook Server)
    print(f"🚀 [Server] جاري تشغيل سيرفر الـ Webhook على المنفذ {port}...")
    app.run(host="0.0.0.0", port=port)
