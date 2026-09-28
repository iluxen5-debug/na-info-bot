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

    # Поля, которые ПОЛНОСТЬЮ СКРЫВАЕМ из сообщения
    ignored = [
        'formid', 'formname', 'tranid', 'tildaspec', 'COOKIES',
        'messenger-type', 'messenger-id'
    ]

    file_url = None
    user_text = ""
    other_fields = []

    for key, value in data.items():
        if key in ignored or not str(value).strip():
            continue
        
        val = str(value).strip()
        
        # Поиск ссылки на фото
        if not file_url and (val.startswith('http') and ('tupwidget' in val or 'tilda' in val)):
            file_url = fix_tilda_url(val)
            continue
        
        # Поле с текстом сообщения
        if key in ['Текст_объявления', 'Text', 'message', 'Message', 'Сообщение']:
            user_text = val
        else:
            # Для всех остальных полей (Имя, Телефон и т.д.)
            other_fields.append(f"<b>{html.escape(key)}:</b> {html.escape(val)}")

    text_parts = ["📩 <b>Новая заявка:</b>\n"]

    if other_fields:
        text_parts.extend(other_fields)
        text_parts.append("") # Разделитель

    if user_text:
        # Объединяем абзацы в единый сплошной плашечный блок.
        # Это делает текст 100% кликабельным в 1 касание на Android, ПК и Unigram без меню!
        clean_copiable_text = re.sub(r'[\r\n]+', '  •  ', user_text)
        
        text_parts.append("👇 <b>Нажмите на текст ниже, чтобы скопировать (1 клик):</b>")
        text_parts.append(f"<code>{html.escape(clean_copiable_text)}</code>")

    caption = "\n".join(text_parts)

    main_payload = {
        "chat_id": CHAT_ID,
        "text": caption,
        "parse_mode": "HTML"
    }
    
    if file_url:
        main_payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🖼 Открыть фото", "url": file_url}]]
        }

    # Отправка текста
    requests.post(f"{TELEGRAM_API}/sendMessage", json=main_payload)

    # Отправка фото при наличии
    if file_url:
        photo_res = requests.post(f"{TELEGRAM_API}/sendPhoto", json={
            "chat_id": CHAT_ID,
            "photo": file_url
        })
        
        if photo_res.status_code != 200:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                img_data = requests.get(file_url, headers=headers, timeout=20).content
                if len(img_data) > 5000:
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
