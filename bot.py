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

# ---- 3. منابع خبری به‌روزرسانی‌شده (RSS Feeds) ----
NEWS_FEEDS = {
    "Quincy Institute": "https://responsiblestatecraft.org/feed/",
    "Carnegie Endowment": "https://carnegieendowment.org/rss/page/analysis",
    "Harvard Business Review": "https://feeds.feedburner.com/harvardbusiness",
    "The Economist (International)": "https://www.economist.com/international/rss.xml",
    "The Economist (Business)": "https://www.economist.com/business/rss.xml",
    "The Economist (Finance & Economics)": "https://www.economist.com/finance-and-economics/rss.xml",
    "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss"
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

def extract_link(entry):
    """استخراج هوشمند لینک از فیلدهای مختلف RSS"""
    # 1. برحصور مستقیم link
    link = entry.get("link", "")
    if link and isinstance(link, str) and link.startswith("http"):
        return link

    # 2. بررسی ساختار لیستی link
    links = entry.get("links", [])
    if links and isinstance(links, list):
        for l in links:
            href = l.get("href", "")
            if href and href.startswith("http"):
                return href

    # 3. بررسی id یا guid (چون در اکونومیست گاهی لینک در id قرار دارد)
    entry_id = entry.get("id", "")
    if entry_id and entry_id.startswith("http"):
        return entry_id

    guid = entry.get("guid", "")
    if guid and guid.startswith("http"):
        return guid

    return None

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

def fetch_feed_custom(url):
    """دریافت فید RSS با هدر مرورگر برای جلوگیری از مسدود شدن"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        return feedparser.parse(response.content)
    except Exception as e:
        print(f"خطا در دریافت فید از {url}: {e}")
        return feedparser.parse(url)

def process_feeds():
    """بررسی اخبار جدید"""
    print("در حال بررسی منابع خبری برای مقالات جدید...")

    for source_name, feed_url in NEWS_FEEDS.items():
        try:
            feed = fetch_feed_custom(feed_url)

            if not feed.entries:
                print(f"⚠️ منبع {source_name} ورودی جدیدی نداشت یا فید آن خالی است.")
                continue

            # بررسی ۲ خبر آخر از هر منبع
            for entry in reversed(feed.entries[:2]):
                link = extract_link(entry)
                title_en = entry.get("title", "").strip()
                
                # اگر لینک پیدا نشد یا خبر تکراری بود، رد شو
                if not link or not title_en or link in SEEN_LINKS:
                    continue

                # استخراج خلاصه
                summary_raw = entry.get("summary", "") or entry.get("description", "")
                summary_en = clean_html(summary_raw)[:300]

                print(f"📰 خبر جدید پیدا شد از [{source_name}]: {title_en[:30]}...")

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
                    
                    if len(SEEN_LINKS) > MAX_MEMORY:
                        SEEN_LINKS.pop()

                    time.sleep(3)

        except Exception as e:
            print(f"خطا در پردازش منبع {source_name}: {e}")

def news_loop():
    """حلقه زمان‌بندی بررسی اخبار (هر ۱۵ دقیقه)"""
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
