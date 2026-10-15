import os
import sys
import multiprocessing
import time
from webhook_server import app
from data_stream import start_stream
from screener import run_screener

def run_stream_process():
    try:
        print("⚡ [Process] جاري تشغيل بث بيانات IEX المباشرة...", flush=True)
        start_stream()
    except Exception as e:
        print(f"❌ خطأ في عملية البث: {e}", file=sys.stderr, flush=True)

def run_screener_loop():
    """تشغيل ماسح الأسهم بشكل دوري كل 5 دقائق"""
    print("🔍 [Screener] جاري إطلاق ماسح الأسهم التلقائي...", flush=True)
    while True:
        try:
            run_screener()
        except Exception as e:
            print(f"❌ خطأ أثناء تنفيذ الماسح: {e}", file=sys.stderr, flush=True)
        time.sleep(300) # الانتظار 5 دقائق بين كل عملية مسح

if __name__ == "__main__":
    # 1. إطلاق عملية بث الأسعار
    stream_process = multiprocessing.Process(target=run_stream_process, daemon=True)
    stream_process.start()

    # 2. إطلاق عملية مسح الأسهم المباشرة
    screener_process = multiprocessing.Process(target=run_screener_loop, daemon=True)
    screener_process.start()

    # 3. تشغيل سيرفر الـ Webhook
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 [Server] جاري تشغيل Webhook Server على المنفذ {port}...", flush=True)
    app.run(host="0.0.0.0", port=port)
