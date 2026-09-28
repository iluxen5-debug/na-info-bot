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
    # Получаем данные из Тильды
    data = request.form.to_dict()
    
    # Игнорируем тестовые запросы
    if data.get('test') == 'test':
        return jsonify({"status": "ok"}), 200

    # Список технических полей, которые мы вообще не показываем
    ignored = [
        'formid', 'formname', 'tranid', 'tildaspec', 'COOKIES',
        'messenger-type', 'messenger-id'
    ]

    file_url = None
    user_text = ""
    contact_info = []

    # Разбираем все пришедшие поля
    for key, value in data.items():
        val = str(value).strip()
        if not val or key in ignored:
            continue
        
        # 1. Проверяем, не ссылка ли это на файл
        if not file_url and (val.startswith('http') and ('tupwidget' in val or 'tilda' in val)):
            file_url = fix_tilda_url(val)
            continue
        
        # 2. Определяем основное сообщение (Текст объявления)
        if key in ['Текст_объявления', 'Text', 'message', 'Message', 'Сообщение', 'text_объявления']:
            user_text = val
        else:
            # 3. Все остальное (Имя, Телефон и т.д.) идет в контакты
            contact_info.append(f"<b>{key}:</b> {val}")

    # --- ОТПРАВКА СООБЩЕНИЯ №1: ЧИСТЫЙ ТЕКСТ ОБЪЯВЛЕНИЯ ---
    if user_text:
        payload1 = {
            "chat_id": CHAT_ID,
            "text": user_text  # Здесь нет никаких HTML тегов, просто текст
        }
        # Если есть фото, прикрепляем кнопку к тексту
        if file_url:
            payload1["reply_markup"] = {
                "inline_keyboard": [[{"text": "🖼 Открыть фото", "url": file_url}]]
            }
        
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload1)
    
    # --- ОТПРАВКА СООБЩЕНИЯ №2: ДАННЫЕ ОТПРАВИТЕЛЯ ---
    if contact_info:
        payload2 = {
            "chat_id": CHAT_ID,
            "text": "📱 <b>Данные отправителя:</b>\n\n" + "\n".join(contact_info),
            "parse_mode": "HTML"
        }
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload2)

    # --- ОТПРАВКА СООБЩЕНИЯ №3: ПОПЫТКА ПРИСЛАТЬ САМО ФОТО ---
    if file_url:
        # Сначала просим Telegram скачать по ссылке
        res = requests.post(f"{TELEGRAM_API}/sendPhoto", json={
            "chat_id": CHAT_ID,
            "photo": file_url
        })
        
        # Если Telegram не смог (ошибка), пробуем скачать сами и отправить файлом
        if res.status_code != 200:
            try:
                h = {"User-Agent": "Mozilla/5.0"}
                img = requests.get(file_url, headers=h, timeout=20).content
                if len(img) > 5000:
                    requests.post(
                        f"{TELEGRAM_API}/sendPhoto",
                        data={"chat_id": CHAT_ID},
                        files={"photo": ("image.jpg", BytesIO(img), "image/jpeg")}
                    )
            except:
                pass

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
