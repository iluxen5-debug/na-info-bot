import html
import re
import urllib.parse
from io import BytesIO
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# --- ВАШИ ДАННЫЕ ---
BOT_TOKEN = "8946727041:AAEG59i90oVSglspSY97RpxP1YHxnoEVIu4"
CHAT_ID = "-1003977168471"
# -------------------

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def fix_tilda_url(url):
    """Исправляет кириллицу и пробелы в ссылках Тильды."""
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path))
    return urllib.parse.urlunparse(parsed._replace(path=path))

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/tilda-webhook", methods=["POST"])
def handle_tilda():
    data = request.form.to_dict()
    if data.get('test') == 'test':
        return jsonify({"status": "ok"}), 200

    ignored = ['formid', 'formname', 'tranid', 'tildaspec', 'COOKIES']
    file_url = None
    text_parts = ["<b>📩 Новая заявка:</b>\n"]

    for key, value in data.items():
        if key in ignored or not str(value).strip():
            continue
        
        val = str(value).strip()
        # Поиск ссылки
        if not file_url and (val.startswith('http') and ('tupwidget' in val or 'tilda' in val)):
            file_url = fix_tilda_url(val)
            continue
        
        text_parts.append(f"<b>{html.escape(key)}:</b> {html.escape(val)}")

    caption = "\n".join(text_parts)

    # 1. Сначала всегда отправляем ТЕКСТ (чтобы заявка не потерялась)
    # Если есть файл, добавим кнопку, если нет - просто текст
    main_payload = {
        "chat_id": CHAT_ID,
        "text": caption,
        "parse_mode": "HTML"
    }
    
    if file_url:
        main_payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🖼 Открыть фото", "url": file_url}]]
        }

    # Отправляем основной текст
    requests.post(f"{TELEGRAM_API}/sendMessage", json=main_payload)

    # 2. Если есть файл, ПЫТАЕМСЯ прислать его как фото (отдельным сообщением для наглядности)
    if file_url:
        # Попытка 1: Просим Telegram скачать по ссылке
        photo_res = requests.post(f"{TELEGRAM_API}/sendPhoto", json={
            "chat_id": CHAT_ID,
            "photo": file_url
        })
        
        # Попытка 2: Если не вышло (ошибка 400), пробуем скачать сами с другими заголовками
        if photo_res.status_code != 200:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                img_data = requests.get(file_url, headers=headers, timeout=20).content
                if len(img_data) > 5000: # Проверка, что это не маленькая ошибка HTML
                    requests.post(
                        f"{TELEGRAM_API}/sendPhoto",
                        data={"chat_id": CHAT_ID},
                        files={"photo": ("image.jpg", BytesIO(img_data), "image/jpeg")}
                    )
            except:
                pass

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
