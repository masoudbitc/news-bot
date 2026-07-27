FROM python:3.10-slim

WORKDIR /app

# کپی فایل نیازها
COPY requirements.txt .

# نصب مستقیم کتابخانه‌ها
RUN pip install --no-cache-dir requests feedparser deep-translator flask

# کپی بقیه فایل‌ها
COPY . .

CMD ["python", "bot.py"]
