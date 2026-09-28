from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ВАШИ ДАННЫЕ (если меняли токен - вставьте новый сюда)
BOT_TOKEN = "8946727041:AAEZE5AV_WPAJ8R7bMK0cGOybv52doF51CQ"
CHAT_ID = "-1003977168471"

@app.route('/tilda-webhook', methods=['POST'])
def handle_tilda():
    data = request.form.to_dict()

    # Игнорируем тестовый пинг от Тильды
    if data.get('test') == 'test':
        return jsonify({"status": "ok"}), 200

    image_url = None
    text_lines = ["<b>📩 Новая заявка с сайта:</b>\n"]

    # Служебные поля, которые не нужно показывать в чате
    ignored_keys = ['formid', 'formname', 'tranid', 'tildaspec', 'COOKIES']

    for key, value in data.items():
        if key in ignored_keys or not str(value).strip():
            continue

        val_lower = str(value).lower()
        # Проверяем, является ли ссылка картинкой
        is_image = (
            val_lower.startswith('http') and 
            any(ext in val_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.heic', '.gif'])
        )

        if is_image and not image_url:
            image_url = value
        else:
            text_lines.append(f"<b>{key}:</b> {value}")

    caption_text = "\n".join(text_lines)

    # Отправка в Телеграм
    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption_text,
            "parse_mode": "HTML"
        }
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption_text,
            "parse_mode": "HTML"
        }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error: {e}")

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
