import asyncio
import os
import re
import tempfile
from pathlib import Path

import yt_dlp


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def _download_sync(url: str) -> dict:
    tmpdir = tempfile.mkdtemp(prefix="djtools_")

    # yt-dlp options for maximum quality SoundCloud download.
    # SoundCloud offers up to 256 kbps AAC on some tracks (Go+), otherwise 128 kbps MP3.
    # We grab the best available stream and re-encode to MP3 at the highest VBR
    # setting (quality 0 ≈ 220–260 kbps) only when the source isn't already MP3,
    # so we never upscale lossy→lossy unnecessarily.
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                # quality 0 = highest VBR (~220-260 kbps); lame will not upscale
                # a 128 kbps source beyond its original bitrate
                "preferredquality": "0",
            }
        ],
        "postprocessor_args": {
            "FFmpegExtractAudio": ["-q:a", "0"],
        },
        "writethumbnail": False,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # After post-processing the extension is .mp3
    files = list(Path(tmpdir).glob("*.mp3"))
    if not files:
        files = list(Path(tmpdir).glob("*.*"))

    if not files:
        raise RuntimeError("Файл не найден после загрузки")

    filepath = str(files[0])

    title = info.get("title") or "Unknown Title"
    artist = info.get("uploader") or info.get("artist") or "Unknown Artist"
    abr = info.get("abr")
    quality_str = f"{int(abr)} kbps" if abr else "максимальное доступное"

    safe_title = _sanitize_filename(title)
    safe_artist = _sanitize_filename(artist)
    filename = f"{safe_artist} - {safe_title}.mp3"

    return {
        "path": filepath,
        "title": title,
        "artist": artist,
        "quality": quality_str,
        "filename": filename,
        "duration": info.get("duration"),
    }


async def download_track(url: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _download_sync, url)
