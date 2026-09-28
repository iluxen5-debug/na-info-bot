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
    try:
        parsed = urllib.parse.urlparse(url)
        path = urllib.parse.quote(urllib.parse.unquote(parsed.path))
        return urllib.parse.urlunparse(parsed._replace(path=path))
    except:
        return url

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/tilda-webhook", methods=["POST"])
def handle_tilda():
    data = request.form.to_dict()
    
    # ЛОГИРОВАНИЕ: Это поможет нам увидеть, что именно присылает Тильда
    print(f"ПОЛУЧЕНЫ ДАННЫЕ: {data}")

    if data.get('test') == 'test':
        return jsonify({"status": "ok"}), 200

    # Технические поля Тильды, которые мы не выводим вообще
    system_fields = ['formid', 'formname', 'tranid', 'tildaspec', 'COOKIES']

    file_url = None
    user_text = ""
    contact_info = []

    # Ключи, которые мы считаем "Основным текстом"
    main_text_keys = ['Текст_объявления', 'Text', 'message', 'Message', 'Сообщение', 'text_объявления']

    for key, value in data.items():
        val = str(value).strip()
        if not val or key in system_fields:
            continue
        
        # 1. Ищем ссылку на файл
        if not file_url and (val.startswith('http') and ('tupwidget' in val or 'tilda' in val)):
            file_url = fix_tilda_url(val)
            continue
        
        # 2. Ищем основной текст объявления
        if key in main_text_keys and not user_text:
            user_text = val
        else:
            # 3. Все остальное (Телефон, Имя, messenger-id и т.д.)
            contact_info.append(f"<b>{key}:</b> {val}")

    # --- СООБЩЕНИЕ №1: ТЕКСТ ОБЪЯВЛЕНИЯ ---
    if user_text:
        payload1 = {"chat_id": CHAT_ID, "text": user_text}
        if file_url:
            payload1["reply_markup"] = {
                "inline_keyboard": [[{"text": "🖼 Открыть фото", "url": file_url}]]
            }
        r1 = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload1)
        print(f"Отправка текста: {r1.status_code}")
    else:
        print("Основной текст не найден в полях заявки.")

    # --- СООБЩЕНИЕ №2: ДАННЫЕ ОТПРАВИТЕЛЯ (все остальные поля) ---
    if contact_info:
        payload2 = {
            "chat_id": CHAT_ID, 
            "text": "📱 <b>Данные отправителя:</b>\n\n" + "\n".join(contact_info),
            "parse_mode": "HTML"
        }
        r2 = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload2)
        print(f"Отправка контактов: {r2.status_code} ({len(contact_info)} полей)")
    else:
        print("Дополнительные поля (контакты) не найдены.")

    # --- СООБЩЕНИЕ №3: ФОТО ---
    if file_url:
        res = requests.post(f"{TELEGRAM_API}/sendPhoto", json={"chat_id": CHAT_ID, "photo": file_url})
        if res.status_code != 200:
            try:
                img = requests.get(file_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).content
                if len(img) > 5000:
                    requests.post(f"{TELEGRAM_API}/sendPhoto", data={"chat_id": CHAT_ID}, 
                                  files={"photo": ("image.jpg", BytesIO(img), "image/jpeg")})
            except Exception as e:
                print(f"Ошибка загрузки фото: {e}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
