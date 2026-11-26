# FitApply 🎯

**ربات هوشمند جستجو، تطبیق و ارسال خودکار رزومه**

### TL;DR (خلاصه در یک نگاه)
فایل **PDF رزومه** را می‌گیرد، آگهی‌های **جابینجا، جاب‌ویژن، ایران‌تلنت** (و **لینکدین / Indeed**) را می‌گردد، میزان تطابق هر شغل را با هوش مصنوعی می‌سنجد و اگر **Fit** بود، از طریق **مرورگر کروم لاگین‌شده خودتان** رزومه و کاور لتر اختصاصی را ارسال می‌کند.

---

### شروع سریع (۳ مرحله)

**۱. نصب و تنظیم:**
```bash
git clone https://github.com/abolfazl-moeini/FitApply.git
cd FitApply
uv sync
cp config.example.yaml config.yaml
```
*(در `config.yaml` کلمات کلیدی، پلتفرم‌ها و مدل زبانی دلخواه — `antigravity` یا `litellm` — را تنظیم کنید. اگر از APIهای استاندارد مثل Gemini/OpenAI استفاده می‌کنید، کلید را در `.env` بگذارید.)*

**۲. باز کردن کروم با پورت دیباگ (یک‌بار لاگین کنید):**
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.fitapply-chrome"
```
در پنجره بازشده وارد اکانت جابینجا، جاب‌ویژن، ایران‌تلنت یا لینکدین شوید.

**۳. اجرا:**
```bash
# اجرای تستی (فرم‌ها پر می‌شوند ولی دکمه نهایی ارسال کلیک نمی‌شود)
uv run fitapply run --resume cv.pdf --dry-run

# اجرای تعاملی (نمایش امتیاز و تایید شما پیش از هر ارسال)
uv run fitapply run --resume cv.pdf

# اجرای تمام‌خودکار
uv run fitapply run --resume cv.pdf --auto
```

---

### دستورات کاربردی

| دستور | کارکرد |
| :--- | :--- |
| `uv run fitapply run --resume cv.pdf` | کشف آگهی، امتیازدهی و ارسال رزومه |
| `uv run fitapply parse --resume cv.pdf` | تست استخراج اطلاعات از فایل PDF رزومه |
| `uv run fitapply status` | مشاهده آمار آگهی‌های بررسی‌شده و ارسال‌شده |

---

### امکانات کلیدی
- **بدون اختراع مجدد چرخ:** ساخته‌شده روی `Playwright`، `PyMuPDF`، `python-jobspy`، `LiteLLM` و `Antigravity SDK`.
- **جلوگیری از ارسال تکراری:** تمام آگهی‌ها در دیتابیس محلی SQLite (`data/jobs.db`) ثبت می‌شوند.
- **پاسخ به سوالات کارفرما:** سوالات فرم‌ها (مثل حقوق درخواستی یا نظام وظیفه) را از روی رزومه و `config.yaml` پر می‌کند.
- **حالت امن پیش‌فرض:** با `--dry-run` یا تایید تعاملی، کنترل کامل دست خودتان است.
