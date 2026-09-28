import html
import re
from io import BytesIO
from urllib.parse import unquote, urlparse

from flask import Flask, request, jsonify
import requests

from PIL import Image, ImageOps, ImageFile

# Позволяет Pillow открывать некоторые нестандартные JPEG
ImageFile.LOAD_TRUNCATED_IMAGES = True

app = Flask(__name__)

BOT_TOKEN = "8946727041:AAEG59i90oVSglspSY97RpxP1YHxnoEVIu4"
CHAT_ID = "-1003977168471"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".heic"
)


def find_url(text):
    """Находит ссылку в значении поля формы."""
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
    """Определяет, похоже ли значение на файл из Тильды."""
    if not url:
        return False

    decoded_url = unquote(url).lower()
    field_name = str(field_name).lower()

    # Файлы, загруженные через формы Тильды
    if "tupwidget.com" in decoded_url:
        return True

    if any(ext in decoded_url for ext in IMAGE_EXTENSIONS):
        return True

    file_words = (
        "фото", "файл", "картин", "изображ",
        "photo", "file", "image", "upload", "attachment"
    )

    return any(word in field_name for word in file_words)


def make_telegram_jpeg(file_bytes):
    """
    Открывает картинку и сохраняет её как обычный JPEG,
    понятный Telegram.
    """
    image = Image.open(BytesIO(file_bytes))

    # Учитываем поворот фото из метаданных
    image = ImageOps.exif_transpose(image)

    # PNG с прозрачностью / палитровые изображения переводим на белый фон
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

    # Telegram принимает фото с суммой ширины и высоты не более 10000 px.
    # Уменьшаем слишком большие изображения.
    max_sum = 9500
    width, height = image.size

    if width + height > max_sum:
        scale = max_sum / (width + height)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        image = image.resize((new_width, new_height), Image.LANCZOS)

    # Сохраняем в стандартный JPEG
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=90,
        optimize=True
    )
    output.seek(0)

    return output


@app.route("/", methods=["GET"])
def home():
    return "Tilda Telegram bot is working", 200


@app.route("/tilda-webhook", methods=["POST"])
def handle_tilda():
    data = request.form.to_dict()

    # Проверочный запрос от Тильды
    if data.get("test") == "test":
        return jsonify({"status": "ok"}), 200

    ignored_keys = [
        "formid",
        "formname",
        "tranid",
        "tildaspec",
        "COOKIES"
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

        # Ссылку на файл не выводим в сообщении:
        # вместо этого скачаем и приложим файл.
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

    # Лимит подписи Telegram у фотографии — 1024 символа
    if len(caption) > 1000:
        caption = caption[:1000] + "..."

    try:
        # Если в форме есть файл
        if file_url:
            print(f"Найден файл: {file_url}")

            file_response = requests.get(
                file_url,
                timeout=60,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )
            file_response.raise_for_status()

            original_file = file_response.content

            parsed_url = urlparse(file_url)
            original_name = unquote(parsed_url.path.split("/")[-1])

            if not original_name:
                original_name = "image.jpg"

            try:
                # Переводим картинку в безопасный JPEG
                jpeg_file = make_telegram_jpeg(original_file)

                telegram_response = requests.post(
                    f"{TELEGRAM_API}/sendPhoto",
                    data={
                        "chat_id": CHAT_ID,
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    files={
                        "photo": (
                            "photo.jpg",
                            jpeg_file,
                            "image/jpeg"
                        )
                    },
                    timeout=90
                )

                print(
                    f"Ответ Telegram / sendPhoto "
                    f"({telegram_response.status_code}): "
                    f"{telegram_response.text}"
                )

                # Если Telegram всё равно не принял фото,
                # отправляем как обычный файл.
                if telegram_response.status_code != 200:
                    print("Не удалось отправить как фото. Отправляем документом.")

                    telegram_response = requests.post(
                        f"{TELEGRAM_API}/sendDocument",
                        data={
                            "chat_id": CHAT_ID,
                            "caption": caption,
                            "parse_mode": "HTML"
                        },
                        files={
                            "document": (
                                original_name,
                                BytesIO(original_file),
                                "application/octet-stream"
                            )
                        },
                        timeout=90
                    )

                    print(
                        f"Ответ Telegram / sendDocument "
                        f"({telegram_response.status_code}): "
                        f"{telegram_response.text}"
                    )

            except Exception as image_error:
                # Если это не картинка или Pillow не смог открыть её —
                # отправляем вложением как файл.
                print(
                    "Не удалось обработать как изображение: "
                    f"{image_error}"
                )

                telegram_response = requests.post(
                    f"{TELEGRAM_API}/sendDocument",
                    data={
                        "chat_id": CHAT_ID,
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    files={
                        "document": (
                            original_name,
                            BytesIO(original_file),
                            "application/octet-stream"
                        )
                    },
                    timeout=90
                )

                print(
                    f"Ответ Telegram / sendDocument "
                    f"({telegram_response.status_code}): "
                    f"{telegram_response.text}"
                )

        # Если в форме нет картинки или файла
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
                f"Ответ Telegram / sendMessage "
                f"({telegram_response.status_code}): "
                f"{telegram_response.text}"
            )

    except Exception as error:
        print(f"ОБЩАЯ ОШИБКА: {error}")

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
