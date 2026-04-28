# DJTools / Диджей Тулз

Telegram-бот для скачивания треков с SoundCloud в максимальном качестве.

## Деплой на Railway

1. Форкни или залей репозиторий на GitHub
2. Создай новый проект в [Railway](https://railway.app) → Deploy from GitHub repo
3. Добавь переменные окружения в Railway Dashboard → Variables:
   - `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
   - `ADMIN_IDS` — Telegram ID администраторов через запятую (узнать у [@userinfobot](https://t.me/userinfobot))
4. Railway автоматически соберёт проект через nixpacks и запустит бота

## Локальный запуск

```bash
cp .env.example .env
# заполни .env

pip install -r requirements.txt
# убедись, что ffmpeg установлен (brew install ffmpeg / apt install ffmpeg)

python main.py
```

## Переменные окружения

| Переменная  | Описание                                           |
|-------------|---------------------------------------------------|
| `BOT_TOKEN` | Токен Telegram-бота                               |
| `ADMIN_IDS` | ID администраторов через запятую, например `123,456` |

## Ограничения

- Telegram Bot API принимает файлы до **50 МБ** — большинство треков укладываются
- SoundCloud бесплатно отдаёт треки в 128 kbps MP3; треки Go+ — до 256 kbps AAC (автоматически)
