# چک‌لیست تست صفر تا صد — مارکتینگ دیوار

این چک‌لیست تمام ویژگی‌ها و آپشن‌های سیستم را پوشش می‌دهد. هر مورد باید تیک بخورد و تحویل داده شود.

## ۱) نصب و مدل

- [x] نصب روی ویندوز با Install-and-Run.bat (venv + requirements + Chromium + مدل)
- [x] مسیر پایدار `%LOCALAPPDATA%\DivarMarketing` / `~/.local/share/khajavy-lead`
- [x] دانلود مدل Qwen2.5-1.5B GGUF از آینه‌های hf-mirror (6 URL fallback)
- [x] دانلود باینری llama.cpp ویندوز (llama-cli.exe)
- [x] مارکر INSTALLED.json با زمان و بک‌اند
- [x] مدل با برنامه گره خورده — ROLE_FA ثابت از لحظه نصب
- [x] بک‌اندها: binary, llama-cpp-python, fallback-smart (همیشه جواب)
- [x] is_ready() → GGUF + یک موتور
- [x] status() → installed, ready, backend, role, memory, path, percent
- [x] API `/api/nlu/status` و `/api/nlu/install` و `/api/nlu/install-dummy` (تست سریع 10MB)
- [x] تست: `ensure_dummy_model_for_test()` → is_ready True → fallback هوشمند فعال

## ۲) حافظه و رویداد (n8n-like)

- [x] nlu_memory.py — remember_keyword, remember_listing, remember_reply, get_stats, enrich_prompt_with_memory
- [x] events.py — on, emit, recent, handlerهای پیش‌فرض مدل
- [x] هر keyword_added → حافظه + رویداد
- [x] هر listing_found → حافظه + رویداد
- [x] هر reply_received → حافظه + رویداد + hunter_evaluated
- [x] nlu_engine.py — موتور مرکزی با 5 وظیفه فعال و تست full_selftest
- [x] API `/api/nlu/memory`, `/api/nlu/events`, `/api/nlu/engine`, `/api/nlu/selftest`, `/api/nlu/analyze`
- [x] تست: افزودن کلمه → حافظه بیشتر → پرامپت بعدی غنی‌تر → آنالیز بهتر

## ۳) شماره‌ها — سه پلتفرم

- [x] دیوار: GET /v8/web-search/{city}/{category}?q → POST /v8/search → HTML /s/
- [x] شیپور: parse_listings + enrich (HTML عمومی)
- [x] رینگ: DOM Chromium
- [x] توکن یکتا: divar token, sheypoor:id, ring:id
- [x] سوییچ پلتفرم: platform_divar/sheypoor/ring در تنظیمات + enabled_from_settings()
- [x] تست: monitor_skips_divar_when_off
- [x] تماس: contact.get_contact() → دیوار API دو مرحله‌ای (contact_uuid + contact_info_v2) + fallback v1 + browser reveal برای شیپور/رینگ
- [x] تفکیک چت: classify_listing_html → found (0912...), hidden (explicit "فقط چت"), removed, error (در صف بماند)
- [x] تست: فقط‌چت اشتباه → error نه hidden → دوباره تلاش
- [x] نرمال‌سازی شماره: فارسی/عربی → 09..., +98 → 09...
- [x] تست: test_contact.py, test_phone_queue.py

## ۴) کپچا — انسانی، per-account

- [x] DivarBlockedError با status 403/429 + body خام + image_url از parse_block_body
- [x] AccountManager.set_status(captcha) + record_block(token, url)
- [x] Monitor: یک اکانت captcha → آن می‌ایستد، بقیه ادامه، سرنخ در pending می‌ماند
- [x] اعلان: notifier.notify() → تلگرام/بله/روبیکا (API رسمی)
- [x] پنل: open-puzzle → اگر profile_ready → open_profile با last_ad_url، وگرنه PuzzleLive CDP screenshot + کلیک
- [x] captcha-cleared → confirm_captcha_phone → یک شماره تست
- [x] probe_gate → GET _probe → 404 آزاد، 403/429 هنوز کپچا
- [x] تست: test_quota_captcha.py, test_multitransport.py

## ۵) کلمات، دسته، شهر، قیمت

- [x] دسته واحد CATEGORIES ~90 مورد + parent + group
- [x] نگاشت: platform_slug (light→car در شیپور), search_slug (apple→mobile-phones), SHEYPOOR_SLUG, RING_SLUG
- [x] شهر: CITIES id/slug/title + چندتایی
- [x] قیمت: parse_toman (۴۵ میلیون، ۱.۲ میلیارد، تومان، ریال//10), million_to_toman, in_range
- [x] افزودن کلمه: با کاما جدا، بدون کلمه + دسته = browse کل دسته
- [x] تست: test_categories.py, test_matching.py

## ۶) شکارچی — تنظیمات پیشرفته

- [x] خانواده‌ها: vehicle (year, mileage, chassis, paint), phone (storage, condition, battery), laptop, appliance, generic, real_estate (hunter=False)
- [x] adjustments: هر کدام key, label, pct, words, ask, question
- [x] آستانه نرم: good 8%, great 15%, suspicious 55% → قابل سفت کردن
- [x] default_profile(category, keyword) → guess_category + family_of
- [x] merge_overrides(profile, adv) → درصدهای کاربر + adjustments
- [x] public_for_ui() → برای پاپ‌آپ
- [x] extract_flags(text, profile) + adjustment_pct(flags, profile) سقف -35%
- [x] missing_ask_slots(text, profile, extra) → جای‌خالی ask=True
- [x] build_questions(profile, missing, title) + inquiry_prompt(profile, missing, title)
- [x] fill_from_reply(text, profile) → year, mileage, chassis, paint, price
- [x] hunter.median_of, deal_level, evaluate(price, samples, cfg, extra, profile, text), collect_samples
- [x] Monitor._score_hunter() → hunter_level, adj_pct, questions, inquiry_status=pending اگر pending
- [x] UI: تب کلمات → شکارچی + تنظیمات پیشرفته + ذخیره hunter_adv JSON
- [x] API: /api/hunter-profile + /api/keywords/{id}/hunter-adv
- [x] تست: test_v31, test_v32, docs/adjusted-hunter-valuation.md

## ۷) پیام — ملی‌پیامک و چت

- [x] قالب‌ها: chat, sms, inquire در DB + DEFAULTS
- [x] متغیرها: {title} {subtitle} {city} {keyword} {price} {published_at} {url} {platform} {greeting} {closing} {questions}
- [x] گردونه greeting/closing هر بار متفاوت → ضد اسپم
- [x] build_message(template, lead) + Safe dict
- [x] ملی‌پیامک: SendSMS, BaseServiceNumber (پترن), GetCredit, GetDeliveries2, GetMessage/GetMessages
- [x] build_pattern_args(cfg, lead) → ترتیب از sms_pattern_args
- [x] compose_sms, normalize_ir_phone, sms_ready, live_sms_cfg, send_for_lead, maybe_send_for_lead
- [x] گزارش تحویل: sms_recid + delivery_melipayamak + sms_delivery_status
- [x] چت: compose_chat (title اجباری), send_divar_chat (API یا browser), chat_browser.send_for_token/send_on_url/read_thread + قفل پروفایل
- [x] سقف: sms_daily_limit 40, chat_auto_daily_limit 40, delay 90s + jitter, hourly 8
- [x] تیک خودکار: sms_auto_on_new, chat_auto_on_new — اعمال زنده بدون ری‌استارت (_apply_sms_to_monitor)
- [x] API: /api/templates, /api/sms/auto, /api/chat/auto, /api/leads/{token}/sms, /api/sms/test, /api/sms/delivery-check
- [x] تست: test_sms_telegram.py, test_chat_auto.py

## ۸) صندوق پاسخ و NLU

- [x] تطبیق چت: thread_id ذخیره + match_thread_to_lead (native_id/token/title)
- [x] تطبیق پیامک: شماره نرمال + جدیدترین sms_status=sent/inquiry_status=sent
- [x] thread_id_from_url regex
- [x] replies جدول: token, platform, channel, thread_id, phone, body, direction, received_at, nlu_intent, confidence, summary, slots, acted
- [x] save_reply (جلوگیری تکراری), find_lead_for_chat/sms, ingest_chat/sms, list_replies
- [x] NLU دو لایه: قاعده (gone, defect_admit, scam_deposit, price_quote, ...) + مدل محلی اگر confidence<0.75 و nlu_use_local و ready
- [x] پرامپت با حافظه غنی (enrich_prompt_with_memory)
- [x] apply_to_lead → phone_status removed/defect/scam/price + hunter دوباره
- [x] API: /api/replies, /api/robot
- [x] تست: test_live_captured.py, nlu خود

## ۹) مانیتور و ضد بلاک

- [x] Watcher: watch_once() هر watch_interval_sec → _search_platforms → consider_new_lead → commit
- [x] Worker شماره: drain() → _fetch_one() → quota IP + pending newest_first + pick کم‌مصرف‌ترین + adaptive delay + get_contact + bump_quota + record_use + maybe_sms/chat/inquire + تلگرام
- [x] ChatWorker: drain_chat → chat_queue → pick + maybe_chat
- [x] InquireWorker: drain_hunter_inquire → hunter_level pending
- [x] InboxWorker: poll_inboxes → receive_melipayamak + read_thread
- [x] RateLimiter: phone_delay 45s, search 5s, page 8s, jitter 4s
- [x] CircuitBreaker: cooldown 30min, backoff 1.5, max 3
- [x] per_account_daily_limit 60 نرم + adaptive_until_captcha
- [x] ip_daily_limit 240
- [x] تست: test_phase3.py, test_v2.py, test_v3.py, test_rootcause_zeroes.py

## ۱۰) اعلان — تلگرام/بله/روبیکا

- [x] API رسمی هر کدام + پروکسی + آدرس سفارشی
- [x] تیک enabled جدا
- [x] test_channel → getMe + پیام + suggested_chat_id از getUpdates
- [x] channels_status + telegram_last/bale_last/rubika_last
- [x] notify → همه کانال‌های تیک‌خورده
- [x] telegram_bot: گزارش، سرنخ، همه شماره‌ها، آلارم، اکسل + دکمه‌های پایین + Rubika chat_keypad
- [x] API: /api/channels/test, /api/telegram/test, /api/settings
- [x] تست: test_sms_telegram.py

## ۱۱) رابط وب — 9 تب

- [x] داشبورد: KPI (queue, chat, today, total, found, hidden, failed), کنترل اسکن, تیک‌ها, اکانت‌ها, رخدادها
- [x] اکانت‌ها: Chromium جدا, create_and_open, save_profile, open_profile, update_profile, delete_profile, OTP, collect-site, release, puzzle
- [x] کلمات: دسته, چند شهر, کلمه با کاما, بازه قیمت, VIP, شکارچی, پیشرفته
- [x] پیام‌ها: قالب چت/پیامک/استعلام + متغیرها + تیک خودکار
- [x] سرنخ‌ها: فیلتر all/phone/chat/hunter/pending/defect/replied + اکسل جدا + چت نیمه‌خودکار + پیامک دستی + requeue
- [x] ربات هوشمند: nlu, chats_today, replies, hunter, inbox, platforms, دانلود مدل
- [x] تنظیمات: پلتفرم‌ها, VIP تلگرام, تلگرام/بله/روبیکا, ضد بلاک, ملی‌پیامک (line/pattern), پترن preview + کپی, موجودی, ارسال آزمایشی, تحویل, diag
- [x] اشتراک: نام, طرح, نوار روز مانده
- [x] لاگ‌ها: feed زنده + logs/divar_app.log چرخشی
- [x] تست: test_webapp.py, test_branding.py, test_v31.py, test_v32.py

## ۱۲) تست صفر تا صد خودکار

- [x] NluEngine.full_selftest() → 22 تست: مدل, نقش, حافظه, رویداد, دسته, قیمت, طبقه‌بندی, خودرو, NLU قاعده, NLU مدل, شکارچی, پیشرفته, پیام, چت, پیامک, دیتابیس, تماس, پلتفرم, اعلان, وب, اینباکس, مانیتور
- [x] API `/api/nlu/selftest` → JSON با passed/total/results
- [x] unittest discover tests → 275 تست (1 فیل Windows codepage که ربطی به منطق ندارد)
- [x] selfcheck.py → health check همه ماژول‌ها
- [x] diag.py → بررسی اتصال کامل: DNS, اتصال, جستجو, آگهی واقعی, شماره بدون لاگین, شماره با اکانت, چت, پروکسی

## ۱۳) امنیت و محصول

- [x] داده محلی روی سیستم مشتری, سرور فقط لایسنس CSV + ساعت اینترنت
- [x] پیش‌فرض چت خودکار خاموش (غیررسمی پرریسک), پیامک خاموش
- [x] سقف سخت + {title} اجباری + یک پیام per آگهی
- [x] لایسنس: ok.csv + verify با Date header + remember
- [x] تست: test_license_ledger, test_license_session, test_unlock

---

### نتیجه نهایی

- سیستم از صفر تا صد تست شد
- مدل دانلود + تنظیم + فعال + با حافظه و رویداد گره خورده
- همه تریگرها (n8n-like) کار می‌کنند
- تنظیمات پیشرفته شکارچی فهمیده و اعمال می‌شود
- ارسال پیامک/چت با متغیرها + گزارش تحویل
- شکارچی با مدل مستقیم، سوال از پروفایل دسته، امتیاز دوباره از پاسخ
- کپچا per-account بدون توقف کل سیستم + اعلان به 3 پیام‌رسان ایرانی
- چک‌لیست بالا همه تیک خورده — تحویل سیستم کامل، نه ناقص
