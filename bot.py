import os
import re
import time
import threading
import requests
import feedparser
from flask import Flask
from deep_translator import GoogleTranslator

# ---- 1. وب‌سرور برای Render و UptimeRobot ----
app = Flask(__name__)

@app.route('/')
def home():
    return "News Bot is running fine!"

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ---- 2. تنظیمات تلگرام ----
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "-1003721340249")

# ---- 3. منابع خبری (RSS Feeds) ----
NEWS_FEEDS = {
    "Quincy Institute": "https://responsiblestatecraft.org/feed/",
    "Carnegie Endowment": "https://carnegieendowment.org/rss/solr/?fa=all",
    "Harvard Business Review": "https://feeds.hbr.org/harvardbusiness",
    "The Economist": "https://www.economist.com/the-world-this-week/rss.xml"
}

# حافظه موقت برای ذخیره ۲۰۰ خبر آخر جهت جلوگیری از تکرار
SEEN_LINKS = set()
MAX_MEMORY = 200

def clean_html(raw_html):
    """پاک‌سازی تگ‌های HTML از متن خلاصه"""
    if not raw_html:
        return ""
    clean_text = re.sub('<[^<]+?>', '', raw_html)
    return clean_text.strip()

def translate_to_persian(text):
    """ترجمه متن به فارسی با پشتیبانی از گوگل"""
    if not text:
        return ""
    try:
        clean_text = text[:1000]
        translated = GoogleTranslator(source='auto', target='fa').translate(clean_text)
        return translated
    except Exception as e:
        print(f"خطا در ترجمه: {e}")
        return text

def send_telegram_message(text):
    """ارسال پیام به کانال تلگرام"""
    if not TOKEN:
        print("خطا: BOT_TOKEN تنظیم نشده است!")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    try:
        res = requests.post(url, data=payload, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"خطا در ارسال به تلگرام: {e}")
        return False

def init_first_run():
    """در اولین اجرای ربات، تمام اخبار موجود را فقط ذخیره می‌کند بدون اینکه به کانال بفرستد"""
    print("در حال همگام‌سازی اولیه و شناسایی اخبار موجود...")
    for source_name, feed_url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                link = entry.get("link", "")
                if link:
                    SEEN_LINKS.add(link)
        except Exception as e:
            print(f"خطا در دریافت اولیه {source_name}: {e}")
    print(f"همگام‌سازی تمام شد. تعداد {len(SEEN_LINKS)} خبر موجود شناسایی شد و به کانال فرستاده نخواهند شد.")

def process_feeds():
    """بررسی اخبار جدید"""
    print("در حال بررسی منابع خبری برای مقالات جدید...")

    for source_name, feed_url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)

            # بررسی از قدیمی به جدید
            for entry in reversed(feed.entries[:5]):
                link = entry.get("link", "")
                title_en = entry.get("title", "").strip()
                
                if not link or not title_en or link in SEEN_LINKS:
                    continue

                # استخراج خلاصه
                summary_raw = entry.get("summary", "") or entry.get("description", "")
                summary_en = clean_html(summary_raw)[:300]

                print(f"📰 خبر جدید پیدا شد: {title_en[:30]}...")

                # ترجمه
                title_fa = translate_to_persian(title_en)
                summary_fa = translate_to_persian(summary_en) if summary_en else ""

                # ساخت قالب پیام
                caption = f"🏛 <b>{source_name}</b>\n\n"
                caption += f"📌 <b>{title_en}</b>\n"
                caption += f"🔹 <b>{title_fa}</b>\n\n"
                
                if summary_fa:
                    caption += f"📝 <i>{summary_fa}</i>\n\n"
                
                caption += f"🔗 <a href='{link}'>مطالعه مقاله کامل در منبع اصلی</a>"

                # ارسال پیام
                if send_telegram_message(caption):
                    print(f"✅ خبر با موفقیت ارسال شد: {title_en[:30]}")
                    SEEN_LINKS.add(link)
                    
                    # اگر حافظه پر شد، قدیمی‌ترها را پاک کن
                    if len(SEEN_LINKS) > MAX_MEMORY:
                        SEEN_LINKS.pop()

                    time.sleep(3)

        except Exception as e:
            print(f"خطا در پردازش منبع {source_name}: {e}")

def news_loop():
    """حلقه زمان‌بندی بررسی اخبار (هر ۱۵ دقیقه)"""
    init_first_run()
    
    while True:
        try:
            process_feeds()
        except Exception as e:
            print(f"خطای غیرمنتظره در حلقه اخبار: {e}")
        
        print("انتظار برای بررسی بعدی (۱۵ دقیقه)...")
        time.sleep(900)

# ---- 4. اجرا ----
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    news_loop()