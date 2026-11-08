# بوت التداول — النسخة المحسّنة (v2)

## ما الذي تغيّر
| المشكلة القديمة | الحل |
|---|---|
| فحص السبريد مبني على أسعار وهمية فيرفض كل الصفقات | عرض/طلب حقيقي من Alpaca (Snapshots) |
| خلط بين الحساب التجريبي والحقيقي | إعداد واحد `PAPER_TRADING` يقرأ من متغيرات البيئة |
| `get_latest_trade` على TradingClient (غير موجودة) | `StockHistoricalDataClient` في `broker.py` |
| 3 محركات تتداول بلا تنسيق | محرك واحد `engine.py` يحل محل screener / trading_bot / data_stream |
| الحالة في الذاكرة وتضيع | قاعدة SQLite مشتركة `state.py` |
| الحالة تتغير عند الإرسال لا التنفيذ | بث `trade_updates` من Alpaca يحدّث الحالة عند التنفيذ الفعلي |
| الوقف يعتمد على جدولة GitHub المتأخرة | أمر Bracket لدى Alpaca في الجلسة الرسمية + مراقبة كل 30 ثانية في الممتد |
| yfinance غير رسمي ويحظر | بيانات Alpaca بطلبات مجمعة |
| قوائم ومعايير مكررة ومتضاربة | قائمة ومعايير واحدة من `config.py` قابلة للتعديل بمتغيرات البيئة |
| قاعدة PDT غير مأخوذة بالحسبان | فحص PDT وحد يومي للصفقات |
| Kill Switch يمنع الشراء فقط | يُلغي الأوامر ويغلق كل المراكز وينبّه |
| كلمة سر Webhook افتراضية مكشوفة | إلزامية، ومقارنة آمنة، والبوابة مغلقة بدونها |
| شراء سهم واحد بالإجبار | الكمية = الأصغر بين الميزانية وحد المخاطرة بالدولار |
| رسالة تليجرام قبل التنفيذ | الرسالة بعد التنفيذ الفعلي، مع رسالة إغلاق بالنتيجة |

## الملفات
- `config.py` الإعدادات · `broker.py` الاتصال بـ Alpaca · `strategy.py` منطق الإشارة
- `risk_engine.py` المخاطر · `order_manager.py` الأوامر · `engine.py` المحرك
- `state.py` الحالة · `alerts.py` تليجرام · `webhook_server.py` بوابة TradingView · `main.py` التشغيل
- `Procfile` أمر التشغيل على Railway · `tests/` اختبارات المنطق

**احذف الملفات القديمة** `screener.py` و `trading_bot.py` و `data_stream.py` و ملفات GitHub Actions (`screener.yml`, `trading_bot.yml`) حتى لا يعمل أكثر من محرك على نفس الحساب.

## التشغيل محليًا
```bash
pip install -r requirements.txt
cp .env.example .env      # واملأ المفاتيح
pytest -q                 # الاختبارات
python main.py
```
يحتاج خادمًا يعمل باستمرار (Railway / Render / VPS) — وليس GitHub Actions.

## النشر على Railway
1. **Variables:** أضف كل متغيرات `.env.example` بقيمك. تأكد أن مفاتيح Alpaca تطابق `PAPER_TRADING`
   (مفاتيح Paper مع `true`، ومفاتيح Live مع `false`) — وإلا تظهر رسالة تفصيلية في السجلات.
2. **Volume:** أضف Volume من تبويب Volumes واربطه بالمسار `/data`، ثم ضع `DB_PATH=/data/bot_state.db`
   حتى لا تضيع حالة الصفقات مع كل إعادة نشر.
3. **أمر التشغيل:** موجود في `Procfile`: `python main.py`.
4. **رابط الـ Webhook لـ TradingView:** `https://<اسم-الخدمة>.up.railway.app/webhook`
   (القيمة في `WEBHOOK_PASSPHRASE` يجب أن تساوي `passphrase` في التنبيه).
5. **أوقف** خدمة Render وملفات GitHub Actions — يجب أن يعمل محرك واحد فقط.

### متغيرات Railway (الأسماء كما يقرأها config.py)
```
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
PAPER_TRADING=true
DATA_FEED=iex
WATCHLIST=
MIN_PRICE=1.50
MAX_PRICE=16.00
MOMENTUM_WINDOW_MIN=5
MIN_MOMENTUM_PCT=3.0
MIN_VOLUME_10M=20000
MAX_SPREAD_PCT=0.60
TRADE_BUDGET_USD=25
MIN_BUDGET_USD=10
RISK_PER_TRADE_USD=1
MAX_OPEN_POSITIONS=2
MAX_DAILY_LOSS_PCT=2.0
MAX_TRADES_PER_DAY=6
SYMBOL_COOLDOWN_MIN=60
TAKE_PROFIT_PCT=4.5
STOP_LOSS_PCT=2.5
ENTRY_TIMEOUT_SEC=90
SCAN_INTERVAL_SEC=30
TRADE_EXTENDED_HOURS=true
DB_PATH=/data/bot_state.db
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WEBHOOK_PASSPHRASE=
PORT=8080
```

### التحقق بعد النشر
- في Deploy Logs يجب أن يظهر سطر يبدأ بـ `connected | paper=True` مع قيمة equity —
  هذا يعني أن المفاتيح صحيحة وبيئية.
- عند إغلاق السوق يجب أن تظهر دورات `closed` كل 5 دقائق تقريبًا.
- راجع جدول `trades_log` في قاعدة البيانات وسجل تليجرام بعد كل صفقة.

## قبل التحويل للحقيقي
1. شغّله على التجريبي أسبوعين على الأقل وراجع السجلات وجدول `trades_log`.
2. على بيانات IEX المجانية ابقِ `MIN_VOLUME_10M` صغيرًا؛ مع SIP ارفعه (مثلًا 200000).
3. إذا كان الحساب أقل من 25 ألف دولار فالأفضل أن يكون **حسابًا نقديًا** لتجنب قاعدة PDT.
4. ثم ضع `PAPER_TRADING=false` مع مفاتيح الحساب الحقيقي (اضغط Regenerate في Alpaca بعد أي تسريب).

## ملاحظات
- في التداول الممتد لا تدعم Alpaca أوامر Bracket أو Stop، لذلك الخروج بأوامر Limit يرسلها المحرك.
- أسهم الزخم الصغيرة عالية المخاطر، والنتائج غير مضمونة.
- `WEBHOOK_PASSPHRASE` فارغة = بوابة TradingView مغلقة تمامًا.
