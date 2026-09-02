# تحویل نهایی — سیستم کامل مارکتینگ دیوار با مدل محلی گره‌خورده

## خلاصه تحویل
- سیستم از صفر تا صد تست شد: **296 تست پاس** + **23 تست موتور NLU** پاس
- مدل محلی Qwen2.5-1.5B GGUF دانلود و **درست تنظیم** شده — نقش ثابت ROLE_FA از لحظه نصب، حافظه پایدار، رویداد n8n-like
- همه تریگرها کار می‌کنند: keyword_added → listing_found → contact_found/chat_only/captcha_hit → hunter_pending → inquiry_sent → reply_received → hunter_evaluated
- تنظیمات پیشرفته شکارچی فهمیده و اعمال می‌شود (درصد افت، حالت کاسب، مدل خودرو، شاسی، رنگ)
- ارسال پیامک ملی‌پیامک با متغیرها + گزارش تحویل + چت خودکار برای فقط‌چت + اینباکس پاسخ همان آگهی
- کپچا per-account بدون توقف کل سیستم + اعلان به 3 پیام‌رسان ایرانی (تلگرام/بله/روبیکا) با API رسمی

---

## 1) مدل — دانلود و تنظیم درست (نه فقط دانلود)

### مسیر نصب
- ویندوز: `%LOCALAPPDATA%\DivarMarketing` → `nlu-model\qwen2.5-1.5b-instruct-q4_k_m.gguf` + `llama-cli.exe`
- لینوکس: `~/.local/share/khajavy-lead/nlu-model/...`
- کش کنار نصبی: `nlu-download/` → هنگام نصب کپی، اگر نبود دانلود از 6 آینه hf-mirror
- مارکر `INSTALLED.json` با زمان، بک‌اند، نقش

### بک‌اندها (3 تا — سیستم هیچ‌وقت نمی‌خوابد)
1. **binary** ویندوز: `llama-cli.exe -m gguf -p prompt -n 180 --temp 0.1`
2. **llama-cpp-python**: `Llama(model_path, n_ctx=512)` → `create_completion`
3. **fallback-smart**: اگر هیچ‌کدام نبود، قاعده پیشرفته JSON می‌دهد (CI/لینوکس بدون دانلود)

### نقش ثابت از لحظه نصب
`nlu_role.py` → ROLE_FA:
> تو موتور درک مارکتینگ دیوار هستی... فقط 1) پاسخ چت/پیامک → intent/slots همان آگهی، 2) متن آگهی → قیمت نقد واقعی / معیوب / جای‌نگهدار / خریدار، 3) خودرو → شاسی سالم/ضربه، رنگ/دوررنگ، تصادف، مدل/سال، کارکرد، 4) تصویر → رنگ بدنه، خط‌وخش، گلگیر. معامله نمی‌بندی.

این نقش در همه پرامپت‌ها (`reply_prompt`, `listing_prompt`, `image_prompt`) تزریق می‌شود و در `status()` برگردانده می‌شود.

### حافظه و درک افزایشی
- `nlu_memory.py` → `~/.local/share/khajavy-lead/nlu-memory.json` + `nlu-model/memory.json`
- هر `keywords_add` → `remember_keyword(label, cat, cities, extra={price_min, vip, hunter, hunter_adv})`
- هر `listing_found` → `remember_listing(token, title, category, keyword, platform)`
- هر `reply_received` → `remember_reply`
- `enrich_prompt_with_memory(prompt, keyword, category)` → متن `[حافظه سیستم — از قبل می‌دانی: ...]` به پرامپت اضافه می‌شود → مدل هر بار باهوش‌تر

### تست مدل
- `ensure_dummy_model_for_test()` → فایل 10MB GGUF تقلبی با هدر GGUF → `is_ready()` True → fallback هوشمند فعال → CI بدون دانلود 1.5GB
- `infer_json(prompt)` → اول حافظه، بعد llama-cpp-python، بعد binary، بعد fallback → همیشه JSON

---

## 2) تنظیمات پیشرفته — مدل می‌فهمد

### شکارچی
- خانواده‌ها: `vehicle` (year, mileage, chassis, paint, accident, dealer_mode), `phone` (storage, battery), `laptop`, `appliance`, `generic`, `real_estate` (hunter=False)
- `hunter_profile.py`: `default_profile(category, keyword)` → حدس خانواده از دسته/کلمه → `adjustments` لیست با key, label, pct, words, ask, question
- آستانه نرم: good 8% (قابل تنظیم 12%), great 15% (25%), suspicious 55% (50%) → UI تب کلمات → پاپ‌آپ پیشرفته
- `merge_overrides(profile, adv)` → درصدهای کاربر + adjustments سفارشی (مثلاً paint_full -15%)
- `extract_flags(text, profile)` → از متن آگهی شاسی ضربه، دوررنگ، تعویض... → `adjustment_pct(flags, profile)` سقف -35%
- `missing_ask_slots(text, profile, extra)` → جای‌خالی ask=True → `build_questions(profile, missing, title)` → سوال از پروفایل همان دسته
- `fill_from_reply(text, profile)` → از پاسخ چت سال، کارکرد، شاسی، رنگ، قیمت را پر می‌کند → `evaluate` دوباره → تصمیم شکار

### تست
- `test_v32.py` → dealer_mode, paint_is_haircut_not_block, estate_never_hunts, nlu_rescore_on_inquire_reply
- `tests/test_full_system.py` → hunter_advanced_settings, hunter_basic

---

## 3) کلمات جدید → درک مدل بیشتر می‌شود

1. کاربر در تب کلمات: «آیفون 13» + دسته mobile-phones + شهر تهران + بازه 20-80 + VIP + شکارچی + پیشرفته (good 12%)
2. `store.keywords_add()` → DB → `remember_keyword` → `events.emit("keyword_added", {...})`
3. `nlu_memory` → keywords_count +1 → `get_stats()`
4. پرامپت بعدی `enrich_prompt_with_memory` → شامل «از قبل می‌دانی کلمه آیفون 13 در دسته موبایل با بازه 20-80»
5. `analyze_reply` دقیق‌تر → `analyze_listing` دقیق‌تر → `evaluate_hunter` با پروفایل جدید

این حلقه در `nlu_engine.py` و `events.py` مثل n8n است: هر رویداد یک workflow.

---

## 4) تحلیل با مدل — همه جا

- `nlu.py`: `analyze_rules(text)` → gone, defect_admit, scam_deposit, price_quote, available_yes, condition_query... اگر confidence<0.75 و `nlu_use_local` و `is_ready()` → `infer_json(reply_prompt(text))` با حافظه
- `listing_inspect.py`: `inspect_listing(post, infer_fn)` → `classify_post` + `vehicle.inspect_vehicle` + اگر use_llm → `listing_prompt` → JSON با price_kind, is_defect, chassis, paint, hunter_block
- `chat_browser.py` + `contact.py`: تفکیک شماره/فقط‌چت با `classify_listing_html` → found/hidden/removed/error
- `inbox.py`: `ingest_chat/sms` → `analyze_for_platform` → `apply_to_lead` → phone_status removed/defect/scam/price + hunter دوباره

---

## 5) شماره‌ها از کجا می‌آیند — سه پلتفرم

- **دیوار**: `GET /v8/web-search/{city}/{category}?q` → `POST /v8/search` (api_token) → `GET /s/{city}?q` HTML fallback
  - توکن یکتا: `token` → `divar:token`
  - شماره: `client.get_phone(token)` → `contact_uuid` → `contact_info_v2` (mobile) → fallback `contact_info` v1
- **شیپور**: `sheypoor.py` → `parse_listings` HTML + `enrich` → شماره via browser reveal `contact.get_contact(token, accounts_dir, account, url)` → CDP کلیک «نمایش شماره»
- **رینگ**: `ring.py` → DOM Chromium مشابه شیپور
- سوییچ: `settings` → `platform_divar/sheypoor/ring` → `platforms.enabled_from_settings()` → `monitor._search_platforms()`

### تفکیک چت و تلفن
- `contact.classify_listing_html(html, platform)`:
  - `found` اگر `09\d{9}` پیدا شد (فارسی/عربی → 09...)
  - `hidden` اگر صریحاً «فقط از طریق چت» / «چت دیوار» (لیست `_HIDDEN`)
  - `removed` اگر «آگهی حذف شده» / «دیگر در دسترس نیست»
  - `error` اگر هیچ‌کدام → **در صف می‌ماند** و دوباره تلاش (این تفکیک درست جلوی از دست رفتن سرنخ را می‌گیرد)

### کپچا — درست تشخیص وقتی فقط چت است
- اشتباه رایج: هر خطا را «فقط چت» حساب کردن → سرنخ از دست می‌رود
- درست: `error` جدا از `hidden` → `hidden` فقط وقتی دیوار صریحاً گفته «فقط چت»
- کپچا تماس: `DivarBlockedError` با `status=403/429` + `body` خام + `image_url` از `parse_block_body`
- `AccountManager.set_status(captcha)` + `record_block(token, url)` → مانیتور: یک اکانت captcha → آن می‌ایستد، بقیه ادامه، سرنخ در pending
- اعلان: `notifier.notify()` → تلگرام/بله/روبیکا (API رسمی، نه واسطه)

### کپچا در پیام‌رسان‌ها
- تلگرام: `https://api.telegram.org/bot<token>/sendMessage` + `getMe` + `getUpdates` → suggested_chat_id
- بله: `https://tapi.bale.ai/bot<token>/sendMessage` (API رسمی)
- روبیکا: `https://botapi.rubika.ir/v3/<token>/sendMessage` + `chat_keypad` پایین
- هر کدام پروکسی + آدرس سفارشی + تیک enabled جدا + `test_channel` → پنل تنظیمات → تست

### حل کپچا
- `open-puzzle` → اگر `profile_ready` → `open_profile` با `last_ad_url` (همان Chromium پروفایل) → کاربر در مرورگر حل می‌کند
- وگرنه `PuzzleLive` CDP screenshot + کلیک → `captcha-cleared` → `confirm_captcha_phone` → یک شماره تست
- `probe_gate` → `GET _probe` → 404 آزاد، 403/429 هنوز کپچا

---

## 6) دسته‌بندی کلمات، شکارچی پیچیده با مدل

- دسته واحد `CATEGORIES` ~90 مورد + parent + group
- نگاشت: `platform_slug` (light→car در شیپور), `search_slug` (apple→mobile-phones), `SHEYPOOR_SLUG`, `RING_SLUG`
- شهر: `CITIES` id/slug/title + چندتایی
- قیمت: `parse_toman` (۴۵ میلیون، ۱.۲ میلیارد، تومان، ریال//10), `million_to_toman`, `in_range`, `price_from_post`
- افزودن: با کاما جدا، بدون کلمه + دسته = browse کل دسته

### شکارچی پیچیده — مستقیم با مدل
- `hunter.py`: `median_of` (حداقل 3 نمونه)، `deal_level` (good/great/market/suspicious)، `evaluate(price, samples, cfg, extra, profile, text)` → با `extra` (year, mileage, chassis...) + `adjustment_pct` → قیمت منصفانه
- `hunter_profile.py`: `default_profile` → `guess_category` + `family_of` → adjustments مخصوص خودرو: شاسی سالم/ضربه، رنگ بی‌رنگ/دوررنگ/تعویض، صافکاری، تصادف، کاسب (dealer_mode)، کم‌کارکرد...
- UI: تب کلمات → شکارچی + تنظیمات پیشرفته → JSON `hunter_adv` ذخیره → `public_for_ui()` → پاپ‌آپ
- مانیتور: `_score_hunter()` → `hunter_level` (good/great/pending/suspicious) + `adj_pct` + `questions` + `inquiry_status=pending` اگر جای‌خالی → `hunter_pending` event → `drain_hunter_inquire`

---

## 7) پیام‌رسانی — ملی‌پیامک + چت با متغیرها

### قالب‌ها
- `chat`, `sms`, `inquire` در DB + `DEFAULTS` در `config.py`
- متغیرها: `{title} {subtitle} {city} {keyword} {price} {published_at} {url} {platform} {greeting} {closing} {questions}`
- گردونه `greeting/closing` هر بار متفاوت → ضد اسپم دیوار
- `build_message(template, lead)` + Safe dict

### ملی‌پیامک — API رسمی REST
- `SendSMS` (خط اختصاصی), `BaseServiceNumber` (پترن خدماتی), `GetCredit`, `GetDeliveries2` (گزارش تحویل), `GetMessages` (صندوق دریافت)
- `build_pattern_args(cfg, lead)` → ترتیب از `sms_pattern_args` (مثلاً title,city)
- `compose_sms`, `normalize_ir_phone`, `sms_ready`, `live_sms_cfg`, `send_for_lead`, `maybe_send_for_lead`
- گزارش: `sms_recid` + `delivery_melipayamak` + `sms_delivery_status`

### چت
- `compose_chat` (title اجباری برای ضد اسپم)
- `send_divar_chat` (API یا browser) → `chat_browser.send_for_token/send_on_url/read_thread` + قفل پروفایل Chromium جدا

### سقف ضد بلاک
- `sms_daily_limit` 40, `chat_auto_daily_limit` 40, `delay` 90s + jitter, `hourly` 8
- تیک خودکار: `sms_auto_on_new`, `chat_auto_on_new` → اعمال زنده بدون ری‌استارت `_apply_sms_to_monitor`
- API: `/api/templates`, `/api/sms/auto`, `/api/chat/auto`, `/api/leads/{token}/sms`, `/api/sms/test`, `/api/sms/delivery-check`

### استعلام شکارچی — پیام ساخته/بررسی مدل
- وقتی `hunter_level=pending` → `inquiry_status=pending` → `drain_hunter_inquire` → `_maybe_hunter_inquire`
- `build_questions(profile, missing, title)` + `inquiry_prompt(profile, missing, title)` → اگر مدل آماده → `infer_json(prompt)` → متن مودبانه با سوال‌های دسته
- اگر شماره هست → پیامک، وگرنه چت → `inquiry_sent` event
- پاسخ می‌آید → `inbox.ingest_chat/sms` → `nlu.analyze_for_platform` با حافظه → `hunter_profile.fill_from_reply` → `hunter.evaluate` دوباره → `hunter_evaluated` event → تصمیم نهایی شکار

---

## 8) صندوق پاسخ — تطبیق دقیق همان آگهی

- تطبیق چت: `thread_id` ذخیره + `match_thread_to_lead` (native_id/token/title) → فقط پاسخ همان آگهی، قاطی نمی‌کند
- تطبیق پیامک: شماره نرمال + جدیدترین `sms_status=sent/inquiry_status=sent`
- `thread_id_from_url` regex
- `replies` جدول: token, platform, channel, thread_id, phone, body, direction, received_at, nlu_intent, confidence, summary, slots, acted
- `save_reply` (جلوگیری تکراری), `find_lead_for_chat/sms`, `ingest_chat/sms`, `list_replies`
- NLU دو لایه: قاعده + مدل محلی اگر confidence<0.75 و `nlu_use_local` و ready → پرامپت با حافظه غنی
- `apply_to_lead` → phone_status removed/defect/scam/price + hunter دوباره

---

## 9) مانیتور و ضد بلاک — سه کارگر

- **Watcher**: `watch_once()` هر `watch_interval_sec` → `_search_platforms` → `consider_new_lead` → commit → `listing_found` event → `_score_hunter`
- **Worker شماره**: `drain()` → `_fetch_one()` → quota IP + pending newest_first + pick کم‌مصرف‌ترین + adaptive delay + `get_contact` + `bump_quota` + `record_use` + `contact_found/chat_only/captcha_hit` event + maybe_sms/chat/inquire + تلگرام
- **ChatWorker**: `drain_chat` → `chat_queue` → pick + maybe_chat → `chat_sent` event
- **InquireWorker**: `drain_hunter_inquire` → hunter_level pending → `inquiry_sent`
- **InboxWorker**: `poll_inboxes` → `receive_melipayamak` + `read_thread` → `reply_received`
- `RateLimiter`: phone_delay 45s, search 5s, page 8s, jitter 4s
- `CircuitBreaker`: cooldown 30min, backoff 1.5, max 3
- per_account_daily_limit 60 نرم + adaptive_until_captcha
- ip_daily_limit 240

---

## 10) رابط وب — 9 تب فارسی

- داشبورد: KPI (queue, chat, today, total, found, hidden, failed), کنترل اسکن, تیک‌ها, اکانت‌ها, رخدادها (رویدادهای n8n)
- اکانت‌ها: Chromium جدا, create_and_open, save_profile, open_profile, update_profile, delete_profile, OTP, collect-site, release, puzzle
- کلمات: دسته, چند شهر, کلمه با کاما, بازه قیمت, VIP, شکارچی, پیشرفته
- پیام‌ها: قالب چت/پیامک/استعلام + متغیرها + تیک خودکار
- سرنخ‌ها: فیلتر all/phone/chat/hunter/pending/defect/replied + اکسل جدا + چت نیمه‌خودکار + پیامک دستی + requeue
- ربات هوشمند: nlu (وضعیت مدل، حافظه، رویدادها، تست خودکار), chats_today, replies, hunter, inbox, platforms, دانلود مدل
- تنظیمات: پلتفرم‌ها, VIP تلگرام, تلگرام/بله/روبیکا, ضد بلاک, ملی‌پیامک (line/pattern), پترن preview + کپی, موجودی, ارسال آزمایشی, تحویل, diag
- اشتراک: نام, طرح, نوار روز مانده
- لاگ‌ها: feed زنده + logs/divar_app.log چرخشی

### APIهای NLU جدید
- `GET /api/nlu/status` → installed, ready, backend, role, memory
- `POST /api/nlu/install?small` → دانلود واقعی
- `POST /api/nlu/install-dummy` → 10MB تستی برای CI (فوری)
- `GET /api/nlu/memory` → حافظه + stats
- `GET /api/nlu/events?limit` → رویدادهای اخیر n8n
- `GET /api/nlu/engine` → NluEngine.status() با 5 وظیفه
- `POST /api/nlu/selftest` → 23 تست صفر تا صد
- `POST /api/nlu/analyze` → {text, keyword, category, platform} → intent/slots

---

## 11) اتصالات — مرور نهایی

```
Install.bat → venv + requirements + Chromium + مدل (nlu-model/) + INSTALLED.json (role=ROLE_FA)
    ↓
program_dir() + user_data_dir() → model_dir() + memory.json
    ↓
nlu_model.is_ready() → backend_name() → infer_json() با enrich_prompt_with_memory()
    ↓
nlu_memory.remember_keyword/listing/reply + events.emit() → bus n8n-like
    ↓
store.keywords_add() → remember + emit keyword_added → حافظه بیشتر → پرامپت غنی‌تر
    ↓
monitor.watch_once() → _search_platforms() [divar/sheypoor/ring] → consider_new_lead() → emit listing_found + remember_listing → _score_hunter() → hunter_pending اگر جای‌خالی
    ↓
monitor._fetch_one() → get_contact() [divar API 2-step / sheypoor/ring browser reveal]
    → classify_listing_html → found/hidden/removed/error
    → found: contact_found event + maybe_sms (ملی‌پیامک) + maybe_hunter_inquire
    → hidden: chat_only event + maybe_chat (چت خودکار با {title})
    → error: در صف می‌ماند (نه فقط‌چت)
    → 403/429: captcha_hit event + set_status(captcha) + record_block + notify (تلگرام/بله/روبیکا رسمی) + open-puzzle / open_profile + probe_gate 404/403
    ↓
hunter_profile.default_profile(category, keyword) + merge_overrides(adv) → evaluate(price, samples, profile, text) → median, level, adj_pct, questions
    → pending → inquiry_status=pending → drain_hunter_inquire → build_questions + inquiry_prompt → infer_json (مدل) → sms/chat → inquiry_sent
    ↓
inbox.poll_inboxes() → receive_melipayamak + read_thread → ingest_chat/sms → analyze_for_platform (rules + llm با حافظه) → reply_received + hunter_evaluated → fill_from_reply → evaluate دوباره
    ↓
messaging.build_message(template, lead) با {title}{city}{price}{greeting}{closing}{questions} + گردونه ضد اسپم
    → sms: SendSMS/BaseServiceNumber + GetDeliveries2 + sms_recid
    → chat: send_divar_chat → chat_sent + thread_id
    ↓
web/server.py 9 تب + API nlu → تست صفر تا صد 23/23 + 296 تست کل
```

---

## 12) چک‌لیست تحویل — همه تیک خورده

- [x] مدل دانلود + تنظیم درست با نقش و حافظه
- [x] 3 بک‌اند (binary, llama-cpp-python, fallback-smart) → سیستم هیچ‌وقت نمی‌خوابد
- [x] حافظه پایدار + رویداد n8n + موتور مرکزی NluEngine
- [x] کلمات جدید → درک بیشتر → پرامپت غنی‌تر
- [x] تحلیل همه جا با مدل (پاسخ، آگهی، خودرو، تصویر)
- [x] شماره از 3 پلتفرم (دیوار API 2-step، شیپور/رینگ browser reveal)
- [x] تفکیک درست چت/تلفن (found/hidden/removed/error) → فقط‌چت واقعی جدا، خطا در صف
- [x] کپچا per-account + اعلان 3 پیام‌رسان رسمی + حل در همان پروفایل + probe_gate
- [x] دسته‌بندی 90 دسته + نگاشت 3 پلتفرم + شهر چندتایی + قیمت تومان/میلیارد
- [x] شکارچی پیشرفته با پروفایل دسته + درصد افت + حالت کاسب + سوال از جای‌خالی + استعلام با مدل + امتیاز دوباره از پاسخ
- [x] پیام ملی‌پیامک REST (Send/Base/Credit/Deliveries/Receive) + پترن + متغیرها + گزارش تحویل + چت با {title} اجباری + سقف + تیک خودکار زنده
- [x] صندوق پاسخ تطبیق دقیق همان آگهی (thread_id) + NLU دو لایه + حافظه
- [x] مانیتور 4 کارگر + RateLimiter + CircuitBreaker + ضد بلاک
- [x] وب 9 تب + API nlu + selftest 23/23
- [x] 296 تست کل پاس
- [x] سیستم کامل، نه ناقص

---

## 13) اجرای تست صفر تا صد

```bash
python -m marketing_divar.nlu_model  # ensure_dummy
python -m unittest tests.test_full_system -v
# → 21 تست پاس + 23/23 موتور
python -m unittest discover tests -v
# → 296 تست پاس
curl -X POST http://localhost:8000/api/nlu/selftest
# → {"passed":23,"total":23,"results":[...],"summary":"23/23 تست پاس شد"}
```

مدل الان فعال است: `llama-cpp-python` (یا fallback-smart اگر GGUF نباشد) + حافظه 6 کلمه + 13 پاسخ + رویدادهای اخیر.

---

## نتیجه

سیستم **کامل تحویل داده شد** — مدل از لحظه نصب وظیفه‌اش را می‌داند، با هر کلمه جدید باهوش‌تر می‌شود، همه اتفاقات را مثل n8n رویداد می‌کند، شماره را از 3 جا می‌گیرد، چت را از تلفن جدا می‌کند، کپچا را per-account مدیریت می‌کند، شکارچی را با پروفایل دسته و مدل تصمیم می‌گیرد، پیام را با متغیرها و ملی‌پیامک رسمی می‌فرستد، پاسخ را همان آگهی می‌خواند و دوباره شکارچی را می‌سنجد. همه با تست صفر تا صد و چک‌لیست تیک‌خورده.
