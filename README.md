# Marketing — سیستم کاوش و جمع‌آوری سرنخ از دیوار

جستجوی کلمه‌کلیدی در آگهی‌های دیوار، دریافت شماره تماس (لاگین OTP)، دیتابیس سرنخ، پیام چت نیمه‌خودکار — طراحی‌شده برای «بلاک نشدن».

## مستندات
- 📄 [`docs/feasibility-research.md`](docs/feasibility-research.md) — فاز ۱ و ۲: امکان‌سنجی، لاگین، شماره تماس
- 📄 [`docs/challenges-and-countermeasures.md`](docs/challenges-and-countermeasures.md) — فاز ۳: چالش‌ها (کپچا، بلاک، چت) و راهکارها

## شروع سریع (نیازمند IP ایران)
```bash
pip install -r requirements.txt
cp config.example.json config.json   # سهمیه‌ها و تاخیرها را ببینید

python -m marketing_divar login                            # شماره + کد پیامکی
python -m marketing_divar collect -k "آپارتمان" --city 1    # جمع‌آوری + شماره‌ها
python -m marketing_divar draft -k "آپارتمان"              # پیام چت نیمه‌خودکار
python -m marketing_divar watch -k "املاک" --every 600      # مانیتور دوره‌ای
python -m marketing_divar stats && python -m marketing_divar export --csv leads.csv
```

## لایه‌های ضد بلاک (خلاصه)
| لایه | ابژه |
|---|---|
| تاخیر ≥10s + جیتر بین شماره‌گیری‌ها | `RateLimiter` |
| سهمیه روزانه (پیش‌فرض ۸۰ شماره < سقف ۱۵۰ دیوار) | جدول `quota` در DB |
| تشخیص 429/کپچا → توقف + اعلان + کند شدن | `CircuitBreaker` + `notifier` |
| کپچا = انسان-در-حلقه (اپراتور حل می‌کند) | `interactive` در config |
| پیام چت = متن شخصی‌سازی + ارسال توسط انسان | `draft` |

## وضعیت
- [x] فاز ۱ — تحقیق امکان‌سنجی
- [x] فاز ۲ — لاگین OTP + دیتابیس سرنخ + CSV
- [x] فاز ۳ — ضد بلاک (نرخ/سهمیه/مدارشکن) + مانیتور + پیام چت (۱۹ تست پاس)
- [ ] فاز ۴ — تست زنده روی IP ایران + تنظیم دقیق آستانه‌ها

⚠️ داده‌های شخصی و سشن در `data/` می‌مانند و به گیت راه ندارند.

## چند اکانت + مانیتور لحظه‌ای (فاز ۴)
```bash
python -m marketing_divar accounts login ac1   # ×۴ با سیم‌کارت واقعی
python -m marketing_divar monitor -k "آپارتمان" -k "رهن" --city 1
python -m marketing_divar draft --chat-only     # پیام چت نیمه‌خودکار
```
داخل مانیتور: `status | release ac1 | pause | resume | quit` — هنگام کپچای یک اکانت بقیه بدون توقف کار می‌کنند.

- [x] فاز ۴ — چند اکانت چرخشی، مانیتور لحظه‌ای، کپچای بدون توقف (۲۰ تست، شامل شبیه‌ساز E2E)
