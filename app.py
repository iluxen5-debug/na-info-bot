import html
import re
from io import BytesIO
from urllib.parse import unquote, urlparse

from flask import Flask, request, jsonify
import requests
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

app = Flask(__name__)

# Вставьте ваш действующий токен от BotFather
BOT_TOKEN = "8946727041:AAEG59i90oVSglspSY97RpxP1YHxnoEVIu4"
CHAT_ID = "-1003977168471"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Заголовки, чтобы маскироваться под обычный браузер Chrome
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tilda.cc/"
}

IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".heic"
)

def find_url(text):
    if not text:
        return None
    text = str(text).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    match = re.search(r'https?://[^\s<>"\']+', text)
    if match:
        return match.group(0)
    return None

def is_file_or_image_url(url, field_name=""):
    if not url:
        return False
    decoded_url = unquote(url).lower()
    field_name = str(field_name).lower()

    if "tupwidget.com" in decoded_url or "tilda" in decoded_url:
        return True
    if any(ext in decoded_url for ext in IMAGE_EXTENSIONS):
        return True
    file_words = ("фото", "файл", "картин", "изображ", "photo", "file", "image", "upload")
    return any(word in field_name for word in file_words)

def convert_to_clean_jpeg(file_bytes):
    """Преобразует любое изображение в чистый стандартный JPEG."""
    image = Image.open(BytesIO(file_bytes))
    image = ImageOps.exif_transpose(image)

    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, "white")
        if image.mode == "P":
            image = image.convert("RGBA")
        if image.mode in ("RGBA", "LA"):
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image)
        image = background
    else:
        image = image.convert("RGB")

    max_size = 4096
    if image.width > max_size or image.height > max_size:
        image.thumbnail((max_size, max_size), Image.LANCZOS)

    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    output.seek(0)
    return output

@app.route("/", methods=["GET"])
def home():
    return "Bot is running", 200

@app.route("/tilda-webhook", methods=["POST"])
def handle_tilda():
    data = request.form.to_dict()

    if data.get("test") == "test":
        return jsonify({"status": "ok"}), 200

    ignored_keys = ["formid", "formname", "tranid", "tildaspec", "COOKIES"]
    file_url = None
    text_lines = ["<b>📩 Новая заявка с сайта:</b>\n"]

    for key, value in data.items():
        if key in ignored_keys:
            continue
        val_str = str(value).strip()
        if not val_str:
            continue

        possible_url = find_url(val_str)
        if not file_url and possible_url and is_file_or_image_url(possible_url, key):
            file_url = possible_url
            continue

        safe_key = html.escape(str(key))
        safe_val = html.escape(val_str)
        text_lines.append(f"<b>{safe_key}:</b> {safe_val}")

    caption = "\n".join(text_lines)
    if len(caption) > 1000:
        caption = caption[:1000] + "..."

    if not file_url:
        # Нет файла — отправляем обычный текст
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML"
        }, timeout=30)
        return jsonify({"status": "ok"}), 200

    print(f"Скачиваем файл по ссылке: {file_url}")

    try:
        # Скачиваем файл с эмуляцией реального браузера
        response = requests.get(file_url, headers=BROWSER_HEADERS, timeout=45)
        response.raise_for_status()
        raw_bytes = response.content

        # Если вернулся HTML (ошибка авторизации/доступа), а не файл
        if raw_bytes.startswith(b"<!DOCTYPE") or raw_bytes.startswith(b"<html") or len(raw_bytes) < 500:
            print("Тильда вернула HTML-страницу вместо картинки. Пробуем отправку по прямой ссылке...")
            # Шлем через прямое URL-фото в Telegram
            res = requests.post(f"{TELEGRAM_API}/sendPhoto", json={
                "chat_id": CHAT_ID,
                "photo": file_url,
                "caption": caption,
                "parse_mode": "HTML"
            }, timeout=30)
            
            if res.status_code != 200:
                # Если и так не вышло — шлем текст со ссылкой
                requests.post(f"{TELEGRAM_API}/sendMessage", json={
                    "chat_id": CHAT_ID,
                    "text": f"{caption}\n\n<b>Ссылка на файл:</b> {file_url}",
                    "parse_mode": "HTML"
                }, timeout=30)
            return jsonify({"status": "ok"}), 200

        # Конвертируем в полноценный JPEG
        jpeg_stream = convert_to_clean_jpeg(raw_bytes)

        # Отправляем нормальное фото в Telegram
        res = requests.post(
            f"{TELEGRAM_API}/sendPhoto",
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML"
            },
            files={
                "photo": ("image.jpg", jpeg_stream, "image/jpeg")
            },
            timeout=60
        )
        print(f"Ответ Telegram API: {res.status_code} {res.text}")

    except Exception as e:
        print(f"Ошибка при обработке файла: {e}")
        # Запасной вариант: отправляем сообщение со ссылкой
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": f"{caption}\n\n<b>Ссылка на фото:</b> {file_url}",
            "parse_mode": "HTML"
        }, timeout=30)

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
