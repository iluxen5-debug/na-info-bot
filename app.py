import html
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

BOT_TOKEN = "8946727041:AAEG59i90oVSglspSY97RpxP1YHxnoEVIu4"
CHAT_ID = "-1003977168471"

@app.route('/tilda-webhook', methods=['POST'])
def handle_tilda():
    data = request.form.to_dict()

    # Игнорируем тестовые запросы от Тильды
    if data.get('test') == 'test':
        return jsonify({"status": "ok"}), 200

    image_url = None
    text_lines = ["<b>📩 Новая заявка с сайта:</b>\n"]

    ignored_keys = ['formid', 'formname', 'tranid', 'tildaspec', 'COOKIES']

    for key, value in data.items():
        if key in ignored_keys or not str(value).strip():
            continue

        val_str = str(value)
        val_lower = val_str.lower()

        # Ищем ссылку на фото
        is_image = (
            val_lower.startswith('http') and 
            any(ext in val_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.heic', '.gif'])
        )

        if is_image and not image_url:
            image_url = val_str
        else:
            # Экранируем спецсимволы, чтобы Telegram не выдавал ошибку HTML
            safe_key = html.escape(str(key))
            safe_val = html.escape(val_str)
            text_lines.append(f"<b>{safe_key}:</b> {safe_val}")

    caption_text = "\n".join(text_lines)

    # Пробуем отправить фото с подписью
    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption_text,
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=payload)
        
        # Если Telegram отклонил картинку (например, формат не тот), шлем как текст
        if res.status_code != 200:
            print(f"Ошибка отправки фото: {res.text}. Пробуем отправить текстом...")
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": CHAT_ID,
                "text": caption_text + f"\n\n<b>Ссылка на файл:</b> {image_url}",
                "parse_mode": "HTML"
            }
            res = requests.post(url, json=payload)
    else:
        # Если фото нет — отправляем обычное текстовое сообщение
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption_text,
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=payload)

    # Логируем ответ от Telegram в Render (для отладки)
    print(f"Ответ Telegram API ({res.status_code}): {res.text}")

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
