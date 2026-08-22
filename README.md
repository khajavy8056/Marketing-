# Marketing — سیستم کاوش و جمع‌آوری سرنخ از دیوار

جستجوی کلمه‌کلیدی در آگهی‌های دیوار، دریافت شماره تماس آگهی‌دهندگان (با لاگین کد پیامکی) و مدیریت دیتابیس سرنخ.

## مستندات
- 📄 [`docs/feasibility-research.md`](docs/feasibility-research.md) — تحقیق امکان‌سنجی + یافته‌های شماره تماس
- 🧪 [`scripts/divar_probe.py`](scripts/divar_probe.py) — اسکریپت راستی‌آزمایی اولیه

## شروع سریع (نیازمند IP ایران)
```bash
pip install -r requirements.txt

python -m marketing_divar login                          # شماره + کد پیامکی
python -m marketing_divar collect -k "آپارتمان" --city 1  # جمع‌آوری + شماره‌ها
python -m marketing_divar stats                          # آمار
python -m marketing_divar export --csv leads.csv         # خروجی اکسل
```

## وضعیت
- [x] فاز ۱ — تحقیق امکان‌سنجی
- [x] فاز ۲ — لاگین OTP، جمع‌آور، دیتابیس سرنخ، خروجی CSV (۷ تست آفلاین پاس)
- [ ] فاز ۳ — داشبورد وب + مانیتورینگ زمان‌بندی‌شده + پیام آماده چت

⚠️ داده‌های شخصی (شماره‌ها/سشن) در `data/` ذخیره می‌شوند و به گیت راه نمی‌یابند.
