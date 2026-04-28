import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from queue_manager import queue, RateLimitError

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


def looks_like_soundcloud(text: str) -> bool:
    return any(domain in text for domain in SOUNDCLOUD_DOMAINS)


def _cleanup(track_info: dict) -> None:
    path = track_info.get("path", "")
    # Don't delete files that are still in cache (other users might get them)
    if path and os.path.exists(path):
        try:
            parent = os.path.dirname(path)
            os.unlink(path)
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
        except OSError:
            pass


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎧 <b>DJTools / Диджей Тулз</b>\n\n"
        "Отправь ссылку на трек в SoundCloud — скачаю в максимально доступном качестве.\n\n"
        "<b>Поддерживается:</b>\n"
        "• SoundCloud (треки)\n\n"
        "Просто вставь ссылку и отправь."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
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
    text = message.text.strip()
    user_id = message.from_user.id

    if not looks_like_soundcloud(text):
        await message.answer(
            "❌ Не распознал ссылку на SoundCloud.\n\n"
            "Пример: <code>https://soundcloud.com/artist/track-name</code>"
        )
        return

    # Show queue position before acquiring the semaphore
    position = queue.queue_position()
    if position > 0:
        status_msg = await message.answer(
            f"⏳ В очереди: {position + 1}-й. Подожди немного..."
        )
    else:
        status_msg = await message.answer("⏳ Скачиваю трек...")

    track_info = None
    from_cache = False

    try:
        track_info = await queue.get(text, user_id)
        from_cache = True  # if we get here without downloading, it was cached

        file_size_mb = os.path.getsize(track_info["path"]) / (1024 * 1024)
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

        audio_file = FSInputFile(track_info["path"], filename=track_info["filename"])
        await message.answer_audio(
            audio=audio_file,
            title=track_info["title"],
            performer=track_info["artist"],
            caption=caption,
        )
        await status_msg.delete()

    except RateLimitError as exc:
        minutes = exc.reset_in // 60
        await status_msg.edit_text(
            f"⏱ Слишком много запросов. Попробуй через {minutes} мин."
        )

    except Exception as exc:
        logger.error("Download failed for %s (user %d): %s", text, user_id, exc, exc_info=True)
        await status_msg.edit_text(
            f"❌ Не удалось скачать трек.\n\n<code>{exc}</code>"
        )
        # On error, clean up the file so it's not stuck
        if track_info:
            _cleanup(track_info)


async def main():
    logger.info("Starting DJTools bot (max_concurrent=%d)...", settings.max_concurrent_downloads)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
