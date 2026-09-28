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

# Словарь для замены длинных имен полей из Тильды на короткие
FIELD_MAPPING = {
    'Название_группы': 'Название',
    'Добавить_или_удалить_собрание': 'Что сделать?',
    'День_недели': 'День',
    'Укажи_время_собрания': 'Время',
    'Укажи_формат_если_добавляешь_собрание': 'Формат'
}

def fix_tilda_url(url):
    """Исправляет кириллицу и пробелы в ссылках Тильды."""
    try:
        parsed = urllib.parse.urlparse(url)
        path = urllib.parse.quote(urllib.parse.unquote(parsed.path))
        return urllib.parse.urlunparse(parsed._replace(path=path))
    except:
        return url

def format_contact_link(m_type, m_id):
    """Создает кликабельную ссылку для телефона или телеграма."""
    m_id_clean = str(m_id).strip()
    m_type = str(m_type).lower().strip()
    
    if 'phone' in m_type or m_id_clean.startswith('+'):
        link_val = re.sub(r'[^\d+]', '', m_id_clean)
        return f'<a href="tel:{link_val}">{m_id_clean}</a>'
    
    if 'telegram' in m_type:
        link_val = m_id_clean.replace('@', '')
        return f'<a href="https://t.me/{link_val}">@{link_val}</a>'
    
    return m_id_clean

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/tilda-webhook", methods=["POST"])
def handle_tilda():
    data = request.form.to_dict()
    print(f"ПОЛУЧЕНЫ ДАННЫЕ: {data}")

    if data.get('test') == 'test':
        return jsonify({"status": "ok"}), 200

    system_fields = ['formid', 'formname', 'tranid', 'tildaspec', 'COOKIES']
    main_text_keys = ['Текст_объявления', 'Text', 'message', 'Message', 'Сообщение', 'text_объявления']

    file_url = None
    user_text = ""
    
    m_type = ""
    m_id = ""
    other_fields = []

    for key, value in data.items():
        val = str(value).strip()
        if not val or key in system_fields:
            continue
        
        # 1. Ссылка на фото
        if not file_url and (val.startswith('http') and ('tupwidget' in val or 'tilda' in val)):
            file_url = fix_tilda_url(val)
            continue
        
        # 2. Основной текст
        if key in main_text_keys and not user_text:
            user_text = val
            continue

        # 3. Данные для кликабельной связи
        if key == 'messenger-type':
            m_type = val
            continue
        if key == 'messenger-id':
            m_id = val
            continue
            
        # 4. Переименование длинных ключей
        clean_key = FIELD_MAPPING.get(key, key.replace('_', ' '))
        other_fields.append(f"<b>{clean_key}:</b> {val}")

    # --- СООБЩЕНИЕ №1: ТЕКСТ ОБЪЯВЛЕНИЯ (если есть) ---
    if user_text:
        payload1 = {"chat_id": CHAT_ID, "text": user_text}
        if file_url:
            payload1["reply_markup"] = {
                "inline_keyboard": [[{"text": "🖼 Открыть фото", "url": file_url}]]
            }
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload1)

    # --- СООБЩЕНИЕ №2: ДАННЫЕ ИЗ ФОРМЫ С КОРОТКИМИ ПОДПИСЯМИ ---
    contact_parts = ["📱 <b>Данные отправителя:</b>\n"]
    
    # Кликабельный контакт в начале
    if m_id:
        contact_link = format_contact_link(m_type or "phone", m_id)
        contact_parts.append(f"🔗 <b>Связаться:</b> {contact_link}")
    
    # Добавляем переименованные поля
    if other_fields:
        contact_parts.extend(other_fields)

    if len(contact_parts) > 1:
        payload2 = {
            "chat_id": CHAT_ID, 
            "text": "\n".join(contact_parts),
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        # Если первого текста не было, прикрепим кнопку фото сюда
        if not user_text and file_url:
            payload2["reply_markup"] = {
                "inline_keyboard": [[{"text": "🖼 Открыть фото", "url": file_url}]]
            }
            
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload2)

    # --- СООБЩЕНИЕ №3: ФОТО ---
    if file_url:
        res = requests.post(f"{TELEGRAM_API}/sendPhoto", json={"chat_id": CHAT_ID, "photo": file_url})
        if res.status_code != 200:
            try:
                img = requests.get(file_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).content
                if len(img) > 5000:
                    requests.post(f"{TELEGRAM_API}/sendPhoto", data={"chat_id": CHAT_ID}, 
                                  files={"photo": ("image.jpg", BytesIO(img), "image/jpeg")})
            except:
                pass

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
