# Marketing — سیستم کاوش و بازاریابی سرنخ در دیوار

پروژه ساخت سیستمی برای جستجوی کلمه‌کلیدی در آگهی‌های دیوار، شمارش و
دریافت سرنخ (Lead) از آگهی‌دهندگان و مدیریت تماس با آن‌ها.

## مستندات
- 📄 [`docs/feasibility-research.md`](docs/feasibility-research.md) — تحقیق امکان‌سنجی (فاز ۱)
- 🧪 [`scripts/divar_probe.py`](scripts/divar_probe.py) — اسکریپت راستی‌آزمایی (اجرا روی IP ایران)

## شروع سریع (تست)
```bash
pip install requests
python scripts/divar_probe.py --keyword "آپارتمان" --city tehran
```

## وضعیت
- [x] فاز ۱ — تحقیق امکان‌سنجی
- [ ] فاز ۲ — جمع‌آور آگهی + دیتابیس سرنخ
- [ ] فاز ۳ — داشبورد و پیام آماده (نیمه‌خودکار)
