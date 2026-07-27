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
    """استخراج لینک خبر"""
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

def resolve_google_redirect(google_url):
    """باز کردن لینک گوگل‌نیوز و گرفتن آدرس واقعی سایت کارنگی"""
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        })
        res = session.get(google_url, allow_redirects=True, timeout=10)
        
        # اگر در گوگل ماند، تلاش برای پیدا کردن لینک اصلی داخل HTML
        if "google.com" in res.url:
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                if "carnegieendowment.org" in a['href']:
                    return a['href']
        return res.url
    except Exception as e:
        print(f"خطا در رد کردن گوگل‌نیوز: {e}")
        return google_url

def fetch_carnegie_full_text(google_url):
    """استخراج متن کامل مقاله مستقیم از سایت کارنگی"""
    try:
        real_url = resolve_google_redirect(google_url)
        print(f"🔗 آدرس واقعی استخراج‌شده کارنگی: {real_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        
        res = requests.get(real_url, headers=headers, timeout=12)
        if res.status_code != 200:
            print(f"عدم دسترسی به سایت کارنگی (کد {res.status_code})")
            return None, real_url

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # پاک‌سازی بخش‌های ناخواسته
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.extract()

        # استخراج تمامی پاراگراف‌ها
        paragraphs = soup.find_all('p')
        full_text = []
        
        for p in paragraphs:
            text = p.get_text().strip()
            # فیلتر متون کوتاه و متن‌های مربوط به فوتر
            if len(text) > 50 and not text.startswith("©") and "Carnegie Endowment" not in text:
                full_text.append(text)

        if full_text:
            return "\n\n".join(full_text), real_url
        return None, real_url

    except Exception as e:
        print(f"خطا در استخراج مقاله کارنگی: {e}")
        return None, google_url

def translate_to_persian(text):
    """ترجمه متون به فارسی"""
    if not text:
        return ""
    try:
        chunks = [text[i:i+2500] for i in range(0, len(text), 2500)]
        translated_chunks = []
        for chunk in chunks:
            translated = GoogleTranslator(source='auto', target='fa').translate(chunk)
            translated_chunks.append(translated)
            time.sleep(0.3)
        return "\n\n".join(translated_chunks)
    except Exception as e:
        print(f"خطا در ترجمه: {e}")
        return text

def send_telegram_message(text):
    """ارسال پیام به تلگرام"""
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
    print(f"در حال بررسی منابع خبری...")

    for source_name, feed_url in NEWS_FEEDS.items():
        try:
            feed = fetch_feed_custom(feed_url)

            if not feed.entries:
                print(f"⚠️ هیچ خبری در فید {source_name} یافت نشد.")
                continue

            for entry in reversed(feed.entries[:item_count]):
                link = extract_link(entry)
                title_en = entry.get("title", "").strip()
                
                if not link or not title_en or link in SEEN_LINKS:
                    continue

                summary_en = ""
                final_link = link

                # 1. استخراج اختصاصی مقاله کارنگی
                if source_name == "مؤسسه کارنگی":
                    print(f"📥 در حال تلاش برای استخراج متن کامل کارنگی: {title_en[:30]}...")
                    full_text, real_link = fetch_carnegie_full_text(link)
                    if full_text:
                        summary_en = full_text
                        final_link = real_link

                # 2. پشتیبان: اگر استخراج کامل شکست خورد یا منبع دیگری بود
                if not summary_en:
                    summary_raw = entry.get("summary", "") or entry.get("description", "")
                    summary_en = clean_html(summary_raw)[:350]

                # ترجمه عنوان و متن
                title_fa = translate_to_persian(title_en)
                summary_fa = translate_to_persian(summary_en) if summary_en else ""

                # 3. ارسال به تلگرام
                if source_name == "مؤسسه کارنگی" and len(summary_fa) > 3000:
                    header = f"📌 <b>{title_fa}</b>\n🏛 <b>منبع:</b> {source_name}\n\n"
                    chunks = [summary_fa[i:i+3200] for i in range(0, len(summary_fa), 3200)]
                    
                    for idx, chunk in enumerate(chunks):
                        part_msg = header if idx == 0 else f"📄 <b>ادامه مقاله کارنگی (بخش {idx+1}):</b>\n\n"
                        part_msg += f"📝 {chunk}"
                        if idx == len(chunks) - 1:
                            part_msg += f"\n\n🔗 <a href='{final_link}'>مطالعه مقاله کامل در سایت کارنگی</a>"
                        
                        send_telegram_message(part_msg)
                        time.sleep(1.5)
                    print(f"✅ مقاله کامل کارنگی ارسال شد: {title_en[:30]}")
                else:
                    caption = f"📌 <b>{title_fa}</b>\n\n"
                    if summary_fa:
                        caption += f"📝 {summary_fa}\n\n"
                    
                    caption += f"🏛 <b>منبع:</b> {source_name}\n"
                    caption += f"🔗 <a href='{final_link}'>مطالعه مقاله کامل</a>"

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
