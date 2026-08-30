# منطق کامل سیستم مارکتینگ دیوار — از نصب تا تحویل سرنخ

> این سند چک‌لیست منطق برای مدل و برای تست صفر تا صد است. همه چیز از لحظه نصب تا ارسال پیام و شکارچی توضیح داده شده.

## ۰) نصب و راه‌اندازی

### فلو نصب ویندوز (Install-and-Run.bat)
1. چک پایتون 3.11 — اگر نبود دانلود خودکار
2. ساخت venv در `%LOCALAPPDATA%\DivarMarketing\venv`
3. `pip install -r requirements.txt` — requests, fastapi, uvicorn, playwright, httpx
4. دانلود Chromium اختصاصی برنامه (نه Chrome کاربر) → `app-chromium/`
5. **دانلود مدل محلی Qwen2.5-1.5B GGUF (~1.1GB)** → `nlu-download/` کش، بعد کپی به `nlu-model/` کنار برنامه
   - آینه‌ها: huggingface.co و hf-mirror.com (برای ایران)
   - اگر یکی قطع بود بعدی
   - باینری llama.cpp ویندوز (llama-cli.exe) هم دانلود می‌شود
   - مارکر `INSTALLED.json` با زمان و بک‌اند
6. ساخت پوشه پایدار `%LOCALAPPDATA%\DivarMarketing` — دیتابیس، اکانت‌ها، تنظیمات، لاگ، مدل، حافظه
7. اجرای `python -m marketing_divar.web` → http://localhost:8642
8. صفحه لودینگ نمایشی (240 ثانیه) + ورود لایسنس (CSV آنلاین)

### مسیرهای پایدار
- `user_data_dir()` → ویندوز: `%LOCALAPPDATA%\DivarMarketing`، لینوکس: `~/.local/share/khajavy-lead`
- `DIVAR_DB_PATH` → `divar_leads.db`
- `DIVAR_ACCOUNTS_DIR` → `accounts/<name>/session.json + chromium/`
- `nlu-model/` → `qwen2.5-1.5b-instruct-q4_k_m.gguf + llama-cli.exe + memory.json`
- `nlu-memory.json` → حافظه یادگیری مدل

## ۱) مدل — گره خورده با برنامه، فعال و اکتیو

### نقش ثابت از لحظه نصب (nlu_role.ROLE_FA)
```
تو موتور درک مارکتینگ دیوار هستی. از لحظه اول فقط:
1) پاسخ چت/پیامک را بخوان و نیت را بگو (قیمت، موجود، رد، معیوب، بیعانه مشکوک، حذف‌شده، سؤال)
2) هر پاسخ را فقط به همان آگهی وصل کن؛ آگهی دیگر را قاطی نکن
3) متن آگهی را برای شکارچی بررسی کن: قیمت نقد واقعی، معیوب، جای‌نگهدار، خریدار
4) اگر خودرو است: شاسی سالم/ضربه، رنگ/دوررنگ، تصادف، مدل/سال، کارکرد. قیمت پایین به‌خاطر شاسی/رنگ شکار عالی نیست — ارزش تعدیل می‌شود
5) برای هر دسته (موبایل، لپ‌تاپ، لوازم، خودرو) از پروفایل همان دسته سوال بساز و پاسخ را در همان اسلات‌ها بریز
6) اگر تصویر داده شد فقط آنچه می‌بینی بگو؛ حدس نزن
ممنوع: بستن معامله، قول تخفیف، چانه‌زنی خودکار، ساخت شماره، API ابری، مخلوط دو آگهی
خروجی فقط JSON کوتاه فارسی
```

### بک‌اندها (nlu_model.py)
- **backend 1 — llama.cpp-binary**: ویندوز، `llama-cli.exe -m gguf -p prompt -n 180 -c 512 --temp 0.1`
- **backend 2 — llama-cpp-python**: لینوکس/مک/ویندوز بدون exe، pip package
- **backend 3 — fallback-smart**: همیشه جواب می‌دهد، با قاعده پیشرفته JSON می‌سازد تا سیستم نخوابد (برای CI و تست صفر تا صد)

`is_ready()` → GGUF موجود (>5MB) + یک بک‌اند
`status()` → installed, ready, backend, role, memory stats, path, percent

### حافظه (nlu_memory.py) — مثل n8n
- `remember_keyword(keyword, category, city, extra)` → هر بار کاربر کلمه اضافه می‌کند، درکش اضافه می‌شود
- `remember_listing(token, category, hunter_level, price, is_defect)` → آگهی جدید
- `remember_reply(token, intent, confidence, text, slots)` → پاسخ جدید
- `get_stats()` → تعداد کلمات، دسته‌ها، intentها، شکارچی
- `enrich_prompt_with_memory(base_prompt, keyword, category)` → وقتی کاربر چیزی اضافه می‌کند، حافظه به پرامپت اضافه می‌شود تا آنالیز بهتر شود

ذخیره: `user_data_dir()/nlu-memory.json` + کپی `nlu-model/memory.json`

### رویدادها (events.py) — n8n workflow
- `on(event, handler)` و `emit(event, payload)`
- رویدادها: `keyword_added`, `listing_found`, `contact_found`, `chat_only`, `reply_received`, `hunter_pending`, `hunter_evaluated`, `captcha_hit`, `sms_sent`, `chat_sent`
- مدل به عنوان handler ثبت شده و وظیفه‌اش را می‌داند

### موتور مرکزی (nlu_engine.py) — گره اصلی
- `NluEngine.status()` → نقش، بک‌اند، حافظه، وظایف فعال
- `analyze_reply(text, keyword, category, platform)` → با حافظه غنی
- `analyze_listing(post)` → قیمت نقد/معیوب/خریدار/خودرو/تصویر
- `build_sms_text(template, lead)` و `build_chat_text(template, lead)` → متن با متغیرها + حافظه
- `build_inquiry_text(profile, missing, title)` → سوال استعلام شکارچی از روی پروفایل همان دسته
- `evaluate_hunter(price, samples, extra, text, category, keyword)` → امتیاز شکارچی با افت پروفایل
- `full_selftest()` → تست صفر تا صد 22 مورد

## ۲) شماره‌ها از کجا می‌آیند — سه پلتفرم روی یک پروفایل Chromium

### دیوار (اصلی)
1. جستجو بدون لاگین: `GET /v8/web-search/{city}/{category}?q=keyword` → اگر BLOCKING_VIEW داد → `POST /v8/search/{city}` → اگر باز هم نه → HTML عمومی `divar.ir/s/{city}/{category}?q=`
2. پارس: token, title, subtitle, top, bottom, has_chat, url, price (تومان), price_text
3. تطبیق کلمه: `matching.keyword_hits()` — نرمال‌سازی فارسی/عربی، ی/ک، نیم‌فاصله، ارقام فارسی
4. ذخیره سرنخ: `db.upsert_lead()` — یکتا بر اساس token
5. شماره: `contact.get_contact()` → اگر پلتفرم دیوار و client موجود → `client.get_phone(token)`:
   - گام 1: `GET /v8/posts-v2/web/{token}` → `contact.contact_uuid`
   - گام 2: `POST /v8/postcontact/web/contact_info_v2/{token}` با Bearer JWT + `contact_uuid` → widget_list → موبایل
   - اگر 403/429 → `DivarBlockedError` → اکانت به حالت captcha/cooldown → بقیه اکانت‌ها بدون توقف ادامه
   - اگر صریحاً "فقط چت" → `hidden` → لیست چت
   - اگر آگهی حذف شده → `removed`
   - اگر خطای موقت → `error` → در صف شماره می‌ماند (نه فقط چت اشتباه)

### شیپور و رینگ (multi-platform)
- توکن یکتا: `platform:native_id` (دیوار همان token)
- جستجو: `sheypoor.search()` و `ring.search()` — HTML عمومی یا DOM Chromium
- شماره: `reveal_via_browser(url, accounts_dir, account)` — کلیک "نمایش شماره" در همان پروفایل Chromium لاگین‌شده با CDP
- سوییچ روشن/خاموش: `platforms.enabled_from_settings()` → `platform_divar/sheypoor/ring` در تنظیمات

### تفکیک چت و شماره — جلوگیری از اشتباه
- `classify_listing_html()` → `found` (0912...), `hidden` (explicit_hidden), `removed`, `error` (در صف بماند)
- قانون: فقط وقتی دیوار صریحاً بگوید "فقط چت" → hidden؛ وگرنه error → دوباره تلاش
- این از باگ قدیمی "همه چیز صفر" جلوگیری می‌کند

## ۳) کپچا — انسانی، per-account، بدون توقف کل سیستم

### وقتی به کپچا می‌خوریم
- `DivarBlockedError` با status 403/429 + body خام (تصویر کپچا اگر باشد `parse_block_body()`)
- `AccountManager.set_status(name, "captcha", cooldown_sec=...)` + `record_block(name, body, token, url)`
- `Monitor._fetch_one()` → اگر یک اکانت captcha → آن اکانت می‌ایستد، سرنخ در صف pending می‌ماند، بقیه اکانت‌ها ادامه می‌دهند
- اعلان: `notifier.notify()` → تلگرام/بله/روبیکا (API رسمی هر کدام)
- پنل: تب اکانت‌ها → پاپ‌آپ "حل پازل" → `open-puzzle`:
  - اگر پروفایل Chromium آماده → `open_profile(ACCOUNTS_DIR, name, last_ad_url)` — همان پروفایل لاگین‌شده، سه تب دیوار/شیپور/رینگ
  - وگرنه `PuzzleLive` → CDP screenshot داخل پنل → کلیک روی تصویر = کلیک روی دیوار همان اکانت
- بعد از حل: `captcha-cleared` → `confirm_captcha_phone()` → یک شماره از صف می‌گیرد تا مطمئن شود آزاد شده
- `probe_gate()` → `GET contact_info/_probe` — 404 یعنی آزاد، 403/429 یعنی هنوز کپچا

### پلتفرم‌های پیام‌رسان (روبیکا/بله/تلگرام) برای کپچا و هشدار
- هر سه API رسمی:
  - تلگرام: `https://api.telegram.org/botTOKEN/sendMessage` + پروکسی اختیاری + آدرس سفارشی
  - بله: `https://tapi.bale.ai/botTOKEN/sendMessage`
  - روبیکا: `POST https://botapi.rubika.ir/v3/TOKEN/sendMessage` + `chat_keypad` رسمی
- تیک استفاده جدا: `telegram_enabled/bale_enabled/rubika_enabled`
- تست اتصال: `test_channel()` → `getMe` + پیام "ارتباط برقرار شد" + پیشنهاد Chat ID از `getUpdates`

## ۴) کلمات، دسته‌بندی، شهر

### دسته واحد
- `categories.CATEGORIES` ~ 90 دسته (املاک، وسایل نقلیه، دیجیتال با برندها، خانه، خدمات، شخصی، سرگرمی، حیوانات، صنعتی)
- `platform_slug(canonical, platform)` → نگاشت خودکار شیپور/رینگ (مثلاً light → car در شیپور)
- `search_slug()` → برند موبایل/لپ‌تاپ روی والد (apple → mobile-phones)
- `hunter_allowed()` → املاک شکار نمی‌شود

### شهر
- `cities.CITIES` — id و slug و عنوان فارسی
- چندتایی با Ctrl/Cmd، ذخیره JSON `[1,3]`

### قیمت
- `pricing.parse_toman()` → تومان از "۴۵ میلیون"، "۱.۲ میلیارد"، "۳۰۰,۰۰۰ تومان"، ریال دیوار //10
- `million_to_toman()` → ورودی پنل میلیون تومان → تومان داخلی
- `in_range(price, min, max)` → اگر بازه هست و قیمت نیست → رد (برای جلوگیری از زباله)

### افزودن کلمه
- `store.keywords_add()` → INSERT OR IGNORE + UPDATE اگر تکراری
- تریگر: `remember_keyword()` + `emit("keyword_added")` → حافظه مدل بیشتر می‌شود

## ۵) شکارچی قیمت — پیچیده‌ترین بخش، ارتباط مستقیم مدل

### پروفایل هر دسته (hunter_profile.py)
- خانواده: vehicle, phone, laptop, appliance, generic, real_estate (املاک hunter=False)
- هر خانواده اسلات و adjustments دارد:
  - خودرو: year, mileage_km, chassis, paint + افت: paint_panel -2%, paint_multi -6%, paint_full -10%, chassis_hit -10%, accident -7%, high_km -4%
  - موبایل: storage, condition, battery + افت: like_new 0%, scratches -3%, cracked -10%, no_box -5%, water -12%, board -15%
  - لپ‌تاپ: ram, storage, opened + افت: hdd -6%, screen -8% ...
- آستانه‌ها نرم برای دمو: good 8%, great 15%, suspicious 55% — کاربر در تنظیمات پیشرفته سفت می‌کند
- `default_profile(category, keyword)` → حدس خانواده از روی دسته/کلمه
- `merge_overrides(profile, adv)` → درصدهای کاربر روی پیش‌فرض
- `public_for_ui()` → برای پاپ‌آپ تنظیمات پیشرفته
- `extract_flags(text, profile)` → پرچم‌ها از روی متن آگهی
- `adjustment_pct(flags, profile)` → جمع افت، سقف -35% تا +5%
- `missing_ask_slots(text, profile, extra)` → جای‌خالی‌هایی که باید پرسیده شود (ask=True و در متن نیست)
- `build_questions(profile, missing, title)` → متن سوال ثابت از روی پروفایل، نه حدس آزاد مدل
- `fill_from_reply(text, profile)` → اسلات از پاسخ فروشنده (سال، کارکرد، شاسی، رنگ، قیمت)

### امتیاز (hunter.py)
- `median_of(prices)` → میانه 3+ نمونه
- `deal_level(price, median, good_pct, great_pct, suspicious_pct)` → market/good/great/suspicious
- `evaluate(price, samples, cfg, extra, profile, text)` → 
  - اگر hunter_block/is_placeholder/is_buyer → blocked
  - اگر پروفایل hunter=False → blocked با reason
  - flags = merge(hunter_flags, chassis/paint/accident)
  - adj = adjustment_pct(flags, profile)
  - fair = median * (1+adj/100)
  - discount = (fair-price)/fair
  - missing = missing_ask_slots(...)
  - اگر dealer_mode و missing → pending=True → سوال بساز
  - level = pending ? pending : raw_level
- `collect_samples(con, keyword, city, platform)` → فقط نقد سالم (نه معیوب، نه جای‌نگهدار، نه خریدار)

### ارتباط مدل و شکارچی — کامل
1. آگهی جدید → `inspect_listing()` → قاعده + اگر مبهم LLM → summary_fa + chassis/paint/year/km
2. اگر پایش hunter=True → `Monitor._score_hunter()` → `evaluate()` → hunter_level, adj_pct, questions
3. اگر level=pending → `inquiry_status=pending` → `Monitor._maybe_hunter_inquire()`:
   - اگر شماره هست → پیامک ملی‌پیامک با قالب inquire (متغیر {title} {questions})
   - وگرنه → چت خودکار همان کانال با `compose_chat()`
   - وضعیت `inquiry_status=sent`
4. پاسخ آمد → `inbox.ingest_chat/sms` → `nlu.analyze()` (قاعده + مدل محلی با حافظه) → `apply_to_lead()` → `fill_from_reply()` + `evaluate()` دوباره → level جدید
5. اگر price_quote نقد سالم و خیلی ارزان → great → هشدار ویژه + صدا + تلگرام/بله/روبیکا + اول صف شماره
6. اگر defect_admit → is_defect=1، hunter_level خالی
7. اگر scam_deposit → suspicious
8. مدل هیچ‌وقت معامله نمی‌بندد، فقط intent/slots

### تنظیمات پیشرفته — مدل می‌فهمد چی به چیه
- UI: تب کلمات → "تنظیمات پیشرفته شکارچی" → پاپ‌آپ با good/great/suspicious + dealer_mode + لیست افت‌ها
- ذخیره: `keywords_set_hunter_adv()` → JSON در `keywords.hunter_adv`
- اثر: `hunter_profile_for()` + `merge_overrides()` → در evaluate اعمال
- مثال: کاربر حرفه‌ای خودرو good=12%, great=25%, paint_full=-15% می‌گذارد تا شکار سخت‌گیر شود

## ۶) پیام — ملی‌پیامک و چت خودکار

### قالب‌ها (store.templates)
- chat: `{greeting} آگهی «{title}» رو دیدم... {closing}` + `{questions}` برای شکارچی
- sms: همان + متغیرهای بیشتر
- inquire: `{greeting} برای آگهی «{title}»: {questions} قیمت نقدی نهایی چقدر است؟ {closing}`

### متغیرها (messaging.build_message)
- `{title}` عنوان آگهی (اجباری برای ضد اسپم چت)
- `{subtitle}` توضیح میانی
- `{city}` شهر
- `{keyword}` کلمه کلیدی
- `{price}` قیمت فرمت‌شده (45 میلیون تومان)
- `{published_at}` زمان انتشار
- `{url}` لینک آگهی
- `{platform}` divar/sheypoor/ring
- `{greeting}` گردونه 5 سلام متفاوت (هر بار متفاوت)
- `{closing}` گردونه 5 تشکر متفاوت
- `{questions}` سوالات شکارچی از پروفایل همان دسته

### ملی‌پیامک رسمی
- `sms.send_melipayamak(username, password, to, line, text)` → `POST https://rest.payamak-panel.com/api/SendSMS/SendSMS`
- `send_melipayamak_pattern(username, password, to, bodyId, args)` → `POST .../BaseServiceNumber` با text = args با ; جدا
- `build_pattern_args(cfg, lead)` → ترتیب از `sms_pattern_args` (مثلاً title,city,price)
- `credit_melipayamak()` → موجودی
- `delivery_melipayamak()` → `GetDeliveries2` با recId → delivered/pending/failed
- `receive_melipayamak()` → پولینگ صندوق ورودی (GetMessage/GetMessages) — وب‌هوک روی ویندوز محلی نداریم
- `sms_ready(cfg)` → چک provider, username, password, line/bodyId
- `send_for_lead(cfg, lead, template)` → اگر pattern روشن → pattern، وگرنه خط اختصاصی
- `maybe_send_for_lead()` → اگر `sms_auto_on_new` روشن → همان لحظه

### چت خودکار (فقط‌چت)
- `chat.compose_chat(template, lead)` → شخصی‌سازی با title تا متن‌ها یکسان نباشند
- `send_divar_chat(client, token, text, send_fn)` → اگر client.send_chat دارد API، وگرنه `chat_browser.send_for_token()` → CDP روی همان پروفایل Chromium
- `chat_browser.send_on_url(url, text, accounts_dir, account, token)` → قفل پروفایل → CDP → navigate → JS کلیک چت → paste → ارسال → thread_id
- سقف: `chat_auto_daily_limit` (40)، `chat_auto_delay_sec` (90) + jitter، `chat_auto_hourly_limit` (8)
- اگر حذف شده → status=removed بدون کرش

### تیک‌های خودکار
- `sms_auto_on_new` — به محض پیدا شدن شماره، متن قالب تب پیام‌ها همان لحظه می‌رود
- `chat_auto_on_new` — برای آگهی فقط‌چت، متن با {title} متغیر
- هر دو در داشبورد و تب پیام‌ها و تنظیمات قابل روشن/خاموش — بدون نیاز به ری‌استارت مانیتور (`_apply_sms_to_monitor()`)
- گزارش تحویل پیامک: RecId ذخیره + `GetDeliveries2` + نمایش در سرنخ‌ها
- چت رسید رسمی ندارد — فقط پذیرش ارسال

## ۷) صندوق پاسخ و NLU — تطبیق دقیق با همان آگهی

### تطبیق
- چت: `find_lead_for_chat()` → اول `chat_thread_id` ذخیره‌شده، بعد `match_thread_to_lead()` (native_id در href، token در href، title در page_title)
- پیامک: `find_lead_for_sms()` → شماره نرمال‌شده 09... → جدیدترین سرنخ همان شماره که sms_status=sent یا inquiry_status=sent
- `thread_id_from_url()` → regex برای /chat/, conversation=, thread=, /v/slug/token, /a/id, -id.html

### اینباکس
- `ingest_chat(con, thread, use_llm)` → برای هر پیام آخر 8 تا → `analyze()` → `save_reply()` → `apply_to_lead()`
- `ingest_sms(con, phone, body, received_at, use_llm)` → مشابه
- `save_reply()` → جلوگیری از تکراری (channel+body+thread_id+token+received_at)

### NLU — دو لایه
- قاعده همیشه اول: gone, defect_admit, scam_deposit, price_quote, available_yes/no, refuse_discount, greeting, question, unclear
- اگر confidence <0.75 و `nlu_use_local` روشن و مدل ready → `infer_json(reply_prompt(text))` → JSON → intent/confidence/price/condition/wants_deposit/summary_fa
- مدل فقط JSON کوتاه فارسی می‌دهد، نه مقاله

### عکس‌العمل بعد از تحلیل
- marketing: lead_status=replied
- inquire:
  - price_quote نقد → price واقعی → L3-L4 شکار → great شود یا نه
  - defect_admit → سطل معیوب، ویژه پس گرفته
  - gone → removed
  - scam_deposit → مشکوک + هشدار کلاهبرداری
  - negotiate بدون عدد → در شیت استعلام بماند
  - unclear/کم‌اطمینان → "نیاز به خواندن" در پنل
  - greeting → صبر دور بعد

## ۸) مانیتور لحظه‌ای — سه Worker + ضد بلاک

### Watcher (بدون لاگین، کم‌ریسک)
- هر `watch_interval_sec` (300 ثانیه پیش‌فرض) → `watch_once()` → همه specs فعال → `_search_platforms()` → `consider_new_lead()` → صف pending
- لاگ: "جستجو «kw» / دسته cat: N آگهی" + "🆕 سرنخ جدید"

### Worker شماره (با اکانت‌ها)
- `drain()` → تا اکانت/سهمیه هست → `_fetch_one()`:
  - چک سقف IP کلی (`ip_daily_limit` 240)
  - `pending_phone(limit=1, newest_first=True)` — جدیدترین اول
  - `mgr.pick(db_path, skip=last)` — کم‌مصرف‌ترین فعال، skip اکانت قبلی چت برای چرخش
  - اگر سقف نرم per_account (60) رد شد و adaptive روشن → با فاصله بیشتر ادامه تا دیوار کپچا بخواهد
  - `get_contact(token, client, accounts_dir, account, url)` → found/hidden/removed/error
  - اگر found → `bump_quota(phones)` + `record_use()` + `_maybe_sms()` + `_maybe_hunter_inquire()` + تلگرام
  - اگر hidden → `_maybe_chat()` (اگر چت خودکار روشن)
  - اگر BlockedError → status=captcha + record_block + notify + ادامه بقیه اکانت‌ها

### ChatWorker
- `drain_chat(max_items=8)` → اگر `chat_auto_on_new` روشن → `chat_queue(limit)` → برای هر ردیف → `pick()` + `_maybe_chat()`

### InquireWorker (شکارچی)
- `drain_hunter_inquire(max_items=6)` → `hunter_level=pending AND inquiry_status IN ('','pending')` → `_maybe_hunter_inquire()` → SMS اگر شماره، وگرنه چت

### InboxWorker
- `poll_inboxes()` → اگر sms_inbox_on و provider ملی‌پیامک → `receive_melipayamak()` → `ingest_sms()`
- اگر chat_auto_on_new → برای 6 سرنخ آخر chat_status=sent/inquiry_status=sent → `chat_browser.read_thread()` → `ingest_chat()`

### ضد بلاک
- RateLimiter: phone_delay 45s + jitter 4s, search_delay 5s, page_delay 8s
- CircuitBreaker: cooldown 30min, backoff 1.5, max 3 → توقف تا فردا
- per_account_daily_limit 60 نرم، تا کپچا ادامه
- ip_daily_limit 240
- همه در settings قابل تغییر

## ۹) رابط وب — 9 تب فارسی راست‌چین

1. داشبورد — شروع/توقف + تیک موارد فعلی/خودکارها + KPI + اکانت‌ها + رخدادهای زنده
2. اکانت‌ها — پروفایل Chromium جدا + باز کردن تهران + ذخیره + لاگین OTP + آزادسازی + پازل
3. کلمات کلیدی — دسته واحد + چند شهر + کلمه با کاما + بازه قیمت + VIP + شکارچی + تنظیمات پیشرفته
4. پیام‌ها — قالب چت/پیامک/استعلام + متغیرها + تیک خودکار
5. سرنخ‌ها — فیلتر همه/شماره‌دار/فقط‌چت/شکارچی/در انتظار/معیوب/پاسخ‌ها + خروجی اکسل جدا + چت نیمه‌خودکار + پیامک دستی + برگشت فقط‌چت به صف
6. ربات هوشمند — وضعیت مدل، چت خودکار، صندوق پاسخ، شکارچی، دانلود مدل
7. تنظیمات — سوییچ دیوار/شیپور/رینگ، تلگرام/بله/روبیکا، سهمیه IP، ملی‌پیامک، پترن، بررسی اتصال کامل
8. اشتراک — نام، طرح، نوار روزهای مانده
9. لاگ‌ها — گزارش زنده + فایل `logs/divar_app.log`

## ۱۰) چک‌لیست منطق — برای مدل

- مدل از لحظه نصب می‌داند فقط تحلیل‌گر است، نه معامله‌گر
- هر کلمه جدید → حافظه → پرامپت بعدی غنی‌تر
- هر آگهی → بررسی قیمت نقد/معیوب/جای‌نگهدار/خریدار + خودرو + تصویر
- هر پاسخ → فقط به همان آگهی وصل، intent/slots
- شکارچی → میانه همان پایش → ارزش تعدیل‌شده با افت پروفایل → سطح + جای‌خالی → سوال از پروفایل همان دسته → پیام استعلام با مدل → پاسخ → امتیاز دوباره
- ارسال: شماره → پیامک ملی‌پیامک (خط یا پترن) با متغیرها، فقط‌چت → چت خودکار با {title}، شکارچی pending → همان کانال استعلام
- کپچا → فقط همان اکانت می‌ایستد، بقیه ادامه، اعلان به روبیکا/بله/تلگرام، پازل در همان پروفایل
- همه رویدادها → events.emit → حافظه → مدل فعال

## ۱۱) امنیت و فروش اشتراک

- داده روی سیستم مشتری (محلی) — سرور فقط لایسنس CSV + به‌روزرسانی
- پیش‌فرض چت خودکار خاموش (پرریسک، غیررسمی)، پیامک خودکار خاموش
- سقف‌های سخت + شخصی‌سازی {title} + یک پیام per آگهی → ضد بن
- لایسنس: `license/ok.csv` → username, password, full_name, plan, expires — ساعت از اینترنت (هدر Date)
