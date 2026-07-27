import os
import re
import time
import threading
import requests
import feedparser
from bs4 import BeautifulSoup
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
    "پژوهشکده کویینسی": "https://responsiblestatecraft.org/feed/",
    "مؤسسه کارنگی": "https://news.google.com/rss/search?q=site:carnegieendowment.org&hl=en-US&gl=US&ceid=US:en",
    "هاروارد بیزینس ریویو": "https://feeds.feedburner.com/harvardbusiness",
    "اکونومیست (بین‌الملل)": "https://www.economist.com/international/rss.xml",
    "اکونومیست (تجارت)": "https://www.economist.com/business/rss.xml",
    "اکونومیست (اقتصاد و مالی)": "https://www.economist.com/finance-and-economics/rss.xml",
    "بلومبرگ": "https://feeds.bloomberg.com/markets/news.rss",
    "کانال ۱۳ اسرائیل (اخبار ایران)": "https://news.google.com/rss/search?q=site:13tv.co.il+Iran&hl=en-US&gl=US&ceid=US:en"
}

SEEN_LINKS = set()
MAX_MEMORY = 300

def clean_html(raw_html):
    """پاک‌سازی تگ‌های HTML"""
    if not raw_html:
        return ""
    return re.sub('<[^<]+?>', '', raw_html).strip()

def extract_link(entry):
    """استخراج لینک اصلی خبر"""
    link = entry.get("link", "")
    if link and isinstance(link, str) and link.startswith("http"):
        return link
    links = entry.get("links", [])
    if links and isinstance(links, list):
        for l in links:
            href = l.get("href", "")
            if href and href.startswith("http"):
                return href
    return None

def fetch_carnegie_full_text(url):
    """استخراج متن کامل مقاله از صفحه اصلی سایت کارنگی"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code != 200:
            return None
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # استخراج پاراگراف‌های اصلی بدنه مقاله
        paragraphs = soup.find_all('p')
        full_text = []
        for p in paragraphs:
            text = p.get_text().strip()
            # فیلتر کردن پاراگراف‌های کوتاه یا غیرمرتبط مثل منوها و فوتر
            if len(text) > 60:
                full_text.append(text)
        
        # ترکیب پاراگراف‌ها تا سقف ۳۵00 کاراکتر (محدودیت پیام تلگرام)
        combined_text = "\n\n".join(full_text)
        return combined_text[:3500] if combined_text else None
    except Exception as e:
        print(f"خطا در دریافت متن کامل کارنگی: {e}")
        return None

def translate_to_persian(text):
    """ترجمه متن به فارسی با پشتیبانی از متون طولانی"""
    if not text:
        return ""
    try:
        clean_text = text[:3500]
        return GoogleTranslator(source='auto', target='fa').translate(clean_text)
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
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=15)
        return feedparser.parse(response.content)
    except Exception as e:
        print(f"خطا در دریافت فید: {e}")
        return feedparser.parse(url)

def process_feeds(item_count=3):
    print(f"در حال بررسی منابع خبری (۳ خبر اخیر)...")

    for source_name, feed_url in NEWS_FEEDS.items():
        try:
            feed = fetch_feed_custom(feed_url)

            if not feed.entries:
                continue

            for entry in reversed(feed.entries[:item_count]):
                link = extract_link(entry)
                title_en = entry.get("title", "").strip()
                
                if not link or not title_en or link in SEEN_LINKS:
                    continue

                summary_en = ""

                # اگر منبع کارنگی باشد، متن کامل مقاله را از وب‌سایتش استخراج می‌کنیم
                if source_name == "مؤسسه کارنگی":
                    print(f"📥 در حال استخراج متن کامل مقاله کارنگی: {title_en[:30]}...")
                    summary_en = fetch_carnegie_full_text(link)
                
                # اگر استخراج موفق نبود یا منبع دیگری بود، از همان چکیده RSS استفاده کن
                if not summary_en:
                    summary_raw = entry.get("summary", "") or entry.get("description", "")
                    summary_en = clean_html(summary_raw)[:1000]

                # ترجمه
                title_fa = translate_to_persian(title_en)
                summary_fa = translate_to_persian(summary_en) if summary_en else ""

                # ساخت قالب پیام
                caption = f"📌 <b>{title_fa}</b>\n\n"
                if summary_fa:
                    caption += f"📝 {summary_fa}\n\n"
                
                caption += f"🏛 <b>منبع:</b> {source_name}\n"
                caption += f"🔗 <a href='{link}'>مطالعه مقاله کامل</a>"

                if send_telegram_message(caption):
                    print(f"✅ خبر ارسال شد: {title_en[:30]}")
                    SEEN_LINKS.add(link)
                    if len(SEEN_LINKS) > MAX_MEMORY:
                        SEEN_LINKS.pop()
                    time.sleep(2)

        except Exception as e:
            print(f"خطا در پردازش {source_name}: {e}")

def news_loop():
    process_feeds(item_count=3)
    while True:
        time.sleep(900)
        try:
            process_feeds(item_count=2)
        except Exception as e:
            print(f"خطا در حلقه اصلی: {e}")

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    news_loop()
