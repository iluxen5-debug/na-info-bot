import html
import re
from io import BytesIO
from urllib.parse import unquote, urlparse

from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Вставьте сюда НОВЫЙ токен, который вы получили у BotFather
BOT_TOKEN = "ВСТАВЬТЕ_СЮДА_НОВЫЙ_ТОКЕН"
CHAT_ID = "-1003977168471"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Расширения, которые считаем изображениями
IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".heic"
)

def find_url(text):
    """Достаёт первую ссылку из текста поля Тильды."""
    if not text:
        return None

    text = str(text).strip()

    # Если Тильда прислала просто ссылку
    if text.startswith("http://") or text.startswith("https://"):
        return text

    # Если ссылка находится внутри HTML или текста
    match = re.search(r'https?://[^\s<>"\']+', text)
    if match:
        return match.group(0)

    return None


def is_file_or_image_url(url, field_name=""):
    """Проверяет, похоже ли поле на файл, загруженный через форму."""
    if not url:
        return False

    decoded_url = unquote(url).lower()
    field_name = str(field_name).lower()

    # Типичный домен загрузок Тильды
    if "tupwidget.com" in decoded_url:
        return True

    # Другие варианты хранилищ Тильды
    if "tilda" in decoded_url and (
        "file" in decoded_url or
        "upload" in decoded_url or
        "image" in decoded_url
    ):
        return True

    # Расширение файла
    if any(ext in decoded_url for ext in IMAGE_EXTENSIONS):
        return True

    # Если в названии поля есть слова "фото", "файл", image и т. п.
    file_words = (
        "фото", "файл", "картин", "изображ",
        "photo", "file", "image", "upload", "attachment"
    )
    if any(word in field_name for word in file_words):
        return True

    return False


@app.route("/", methods=["GET"])
def home():
    return "Tilda Telegram bot is working", 200


@app.route("/tilda-webhook", methods=["POST"])
def handle_tilda():
    data = request.form.to_dict()

    # Тест от Тильды
    if data.get("test") == "test":
        return jsonify({"status": "ok"}), 200

    ignored_keys = [
        "formid", "formname", "tranid",
        "tildaspec", "COOKIES"
    ]

    file_url = None
    text_lines = ["<b>📩 Новая заявка с сайта</b>\n"]

    for key, value in data.items():
        if key in ignored_keys:
            continue

        value = str(value).strip()

        if not value:
            continue

        possible_url = find_url(value)

        # Если нашли ссылку на файл — не выводим её текстом,
        # а сохраняем для отправки вложением
        if (
            not file_url
            and possible_url
            and is_file_or_image_url(possible_url, key)
        ):
            file_url = possible_url
            continue

        safe_key = html.escape(str(key))
        safe_value = html.escape(value)
        text_lines.append(f"<b>{safe_key}:</b> {safe_value}")

    caption = "\n".join(text_lines)

    # Ограничение Telegram: подпись к фото не более 1024 символов
    if len(caption) > 1000:
        caption = caption[:1000] + "..."

    try:
        # Есть файл: скачиваем его с Тильды и загружаем в Telegram
        if file_url:
            print(f"Найден файл: {file_url}")

            file_response = requests.get(file_url, timeout=30)
            file_response.raise_for_status()

            content_type = file_response.headers.get(
                "Content-Type", ""
            ).lower()

            parsed_url = urlparse(file_url)
            filename = parsed_url.path.split("/")[-1]
            filename = unquote(filename)

            if not filename:
                filename = "file"

            file_data = BytesIO(file_response.content)

            # Если сервер определил файл как изображение — отправляем фото
            if content_type.startswith("image/") or any(
                filename.lower().endswith(ext)
                for ext in IMAGE_EXTENSIONS
            ):
                telegram_response = requests.post(
                    f"{TELEGRAM_API}/sendPhoto",
                    data={
                        "chat_id": CHAT_ID,
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    files={
                        "photo": (
                            filename,
                            file_data,
                            content_type or "image/jpeg"
                        )
                    },
                    timeout=60
                )

            # Если это не картинка — отправляем файлом
            else:
                telegram_response = requests.post(
                    f"{TELEGRAM_API}/sendDocument",
                    data={
                        "chat_id": CHAT_ID,
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    files={
                        "document": (
                            filename,
                            file_data,
                            content_type or "application/octet-stream"
                        )
                    },
                    timeout=60
                )

        # Если файла нет — обычное сообщение
        else:
            telegram_response = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": caption,
                    "parse_mode": "HTML"
                },
                timeout=30
            )

        print(
            f"Ответ Telegram ({telegram_response.status_code}): "
            f"{telegram_response.text}"
        )

    except Exception as error:
        print(f"ОШИБКА: {error}")

        # На случай ошибки отправляем хотя бы текст
        try:
            error_text = caption

            if file_url:
                error_text += (
                    "\n\n<b>Не удалось прикрепить файл.</b>"
                    f"\nСсылка: {html.escape(file_url)}"
                )

            requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": error_text[:4000],
                    "parse_mode": "HTML"
                },
                timeout=30
            )
        except Exception as second_error:
            print(f"Не удалось отправить даже текст: {second_error}")

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
