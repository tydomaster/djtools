import asyncio
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yt_dlp

from config import settings

TELEGRAM_NATIVE = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus"}

# Priority: 320 kbps MP3 (Go+) → 256 kbps AAC HLS → best available
FORMAT_STRING = "http_mp3_320_url/hls-aac-256-0/bestaudio/best"

# Realistic browser User-Agent — reduces chance of being flagged as a bot
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def _write_cookies_file(tmpdir: str) -> str | None:
    """
    Write cookies to a temp file. Returns the path or None if no cookies configured.
    Accepts SOUNDCLOUD_COOKIES as a base64-encoded Netscape cookies.txt content.
    """
    raw = settings.soundcloud_cookies
    if not raw:
        return None
    try:
        content = base64.b64decode(raw).decode()
    except Exception:
        # Maybe it was pasted as plain text, not base64
        content = raw

    cookie_path = os.path.join(tmpdir, "cookies.txt")
    with open(cookie_path, "w") as f:
        if not content.startswith("# Netscape HTTP Cookie File"):
            f.write("# Netscape HTTP Cookie File\n")
        f.write(content)
    return cookie_path


def _ffprobe_info(filepath: str) -> dict:
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-select_streams", "a:0",
            filepath,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        streams = json.loads(out).get("streams", [])
        if not streams:
            return {}
        s = streams[0]
        return {
            "codec": s.get("codec_name", "").upper(),
            "bitrate_kbps": int(s.get("bit_rate") or 0) // 1000,
            "sample_rate": int(s.get("sample_rate") or 0),
        }
    except Exception:
        return {}


def _convert_to_mp3(src: str, dst: str) -> None:
    subprocess.check_call(
        ["ffmpeg", "-y", "-i", src, "-c:a", "libmp3lame", "-q:a", "0", dst],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _build_ydl_opts(tmpdir: str, cookie_path: str | None) -> dict:
    opts = {
        "format": FORMAT_STRING,
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "writethumbnail": False,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {"User-Agent": USER_AGENT},
        # Small sleep between requests — polite scraping, reduces ban risk
        "sleep_interval": 1,
        "max_sleep_interval": 3,
    }

    if cookie_path:
        # Cookie file (Netscape format) — most stable auth method.
        # Cookies from a Go+ browser session last 6-12 months.
        opts["cookiefile"] = cookie_path
    elif settings.soundcloud_oauth_token:
        # Fallback: raw OAuth token (shorter-lived but still works for months)
        opts["http_headers"]["Authorization"] = f"OAuth {settings.soundcloud_oauth_token}"

    return opts


def _download_sync(url: str) -> dict:
    tmpdir = tempfile.mkdtemp(prefix="djtools_")
    cookie_path = _write_cookies_file(tmpdir)

    with yt_dlp.YoutubeDL(_build_ydl_opts(tmpdir, cookie_path)) as ydl:
        info = ydl.extract_info(url, download=True)

    audio_files = [
        f for f in Path(tmpdir).iterdir()
        if f.is_file() and f.name != "cookies.txt"
    ]
    if not audio_files:
        raise RuntimeError("Файл не найден после загрузки")

    filepath = audio_files[0]
    ext = filepath.suffix.lower()

    if ext not in TELEGRAM_NATIVE:
        mp3_path = filepath.with_suffix(".mp3")
        _convert_to_mp3(str(filepath), str(mp3_path))
        os.unlink(filepath)
        filepath = mp3_path
        ext = ".mp3"

    probe = _ffprobe_info(str(filepath))
    codec = probe.get("codec") or ext.lstrip(".").upper()
    bitrate = probe.get("bitrate_kbps", 0)
    sample_rate = probe.get("sample_rate", 0)

    if bitrate:
        quality_str = f"{codec} {bitrate} kbps"
        if sample_rate:
            quality_str += f" / {sample_rate // 1000} kHz"
    else:
        quality_str = codec or "неизвестно"

    title = info.get("title") or "Unknown Title"
    artist = info.get("uploader") or info.get("artist") or "Unknown Artist"
    safe_filename = f"{_sanitize_filename(artist)} - {_sanitize_filename(title)}{ext}"

    return {
        "path": str(filepath),
        "title": title,
        "artist": artist,
        "quality": quality_str,
        "filename": safe_filename,
        "duration": info.get("duration"),
    }


async def download_track(url: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _download_sync, url)
