import os
import sys
import multiprocessing
from webhook_server import app
from data_stream import start_stream

def run_stream_process():
    try:
        print("⚡ [Process] جاري تشغيل بث بيانات IEX المباشرة...", flush=True)
        start_stream()
    except Exception as e:
        print(f"❌ خطأ في عملية البث: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    # 1. إطلاق عملية بث الأسعار في الخلفية
    stream_process = multiprocessing.Process(target=run_stream_process, daemon=True)
    stream_process.start()

    # 2. تشغيل سيرفر استقبال الـ Webhooks
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 [Server] جاري تشغيل Webhook Server على المنفذ {port}...", flush=True)
    app.run(host="0.0.0.0", port=port)
