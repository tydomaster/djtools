import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from downloader import download_track

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

SOUNDCLOUD_DOMAINS = ("soundcloud.com", "snd.sc")


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def looks_like_soundcloud(text: str) -> bool:
    return any(domain in text for domain in SOUNDCLOUD_DOMAINS)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "🎧 <b>DJTools / Диджей Тулз</b>\n\n"
        "Отправь ссылку на трек в SoundCloud — скачаю в максимально доступном качестве.\n\n"
        "<b>Поддерживается:</b>\n"
        "• SoundCloud (треки)\n\n"
        "Просто вставь ссылку и отправь."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "📖 <b>Как пользоваться</b>\n\n"
        "1. Скопируй ссылку на трек в SoundCloud\n"
        "2. Вставь её в этот чат и отправь\n"
        "3. Получи файл в максимальном качестве\n\n"
        "<b>Пример ссылки:</b>\n"
        "<code>https://soundcloud.com/artist/track-name</code>"
    )


@dp.message(F.text)
async def handle_link(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    text = message.text.strip()

    if not looks_like_soundcloud(text):
        await message.answer(
            "❌ Не распознал ссылку на SoundCloud.\n\n"
            "Пример: <code>https://soundcloud.com/artist/track-name</code>"
        )
        return

    status_msg = await message.answer("⏳ Скачиваю трек, подожди...")
    track_path = None

    try:
        track_info = await download_track(text)
        track_path = track_info["path"]

        file_size_mb = os.path.getsize(track_path) / (1024 * 1024)
        if file_size_mb > 49:
            await status_msg.edit_text(
                f"❌ Файл слишком большой ({file_size_mb:.1f} МБ).\n"
                "Telegram принимает файлы до 50 МБ."
            )
            return

        await status_msg.edit_text("📤 Отправляю файл...")

        caption = (
            f"🎵 <b>{track_info['title']}</b>\n"
            f"👤 {track_info['artist']}\n"
            f"🎚 Качество: {track_info['quality']}"
        )

        audio_file = FSInputFile(track_path, filename=track_info["filename"])
        await message.answer_audio(
            audio=audio_file,
            title=track_info["title"],
            performer=track_info["artist"],
            caption=caption,
        )
        await status_msg.delete()

    except Exception as exc:
        logger.error("Download failed for %s: %s", text, exc, exc_info=True)
        await status_msg.edit_text(
            f"❌ Не удалось скачать трек.\n\n"
            f"<code>{exc}</code>"
        )
    finally:
        if track_path and os.path.exists(track_path):
            try:
                os.unlink(track_path)
                parent = os.path.dirname(track_path)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
            except OSError:
                pass


async def main():
    logger.info("Starting DJTools bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
