import asyncio
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yt_dlp

from config import settings

# Formats Telegram's send_audio accepts natively — no re-encoding needed
TELEGRAM_NATIVE = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus"}

# Priority: 320 kbps MP3 (Go+) → 256 kbps AAC (HLS Go+) → best available
# yt-dlp SoundCloud format IDs:
#   http_mp3_320_url  — 320 kbps MP3, requires OAuth token (Go+)
#   hls-aac-256-0     — 256 kbps AAC HLS, some tracks without auth
#   bestaudio/best    — fallback (usually 128 kbps MP3)
FORMAT_STRING = "http_mp3_320_url/hls-aac-256-0/bestaudio/best"


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def _ffprobe_info(filepath: str) -> dict:
    """Return actual codec/bitrate/samplerate from the file via ffprobe."""
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
        bitrate = int(s.get("bit_rate") or 0) // 1000
        return {
            "codec": s.get("codec_name", "").upper(),
            "bitrate_kbps": bitrate,
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


def _build_ydl_opts(tmpdir: str) -> dict:
    opts = {
        "format": FORMAT_STRING,
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "writethumbnail": False,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    token = settings.soundcloud_oauth_token
    if token:
        # SoundCloud API uses "Authorization: OAuth <token>" for authenticated requests.
        # With a Go+ account token this unlocks the 320 kbps MP3 stream.
        opts["http_headers"] = {"Authorization": f"OAuth {token}"}

    return opts


def _download_sync(url: str) -> dict:
    tmpdir = tempfile.mkdtemp(prefix="djtools_")

    with yt_dlp.YoutubeDL(_build_ydl_opts(tmpdir)) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [f for f in Path(tmpdir).iterdir() if f.is_file()]
    if not files:
        raise RuntimeError("Файл не найден после загрузки")

    filepath = files[0]
    ext = filepath.suffix.lower()

    # Convert only if Telegram won't accept the format
    if ext not in TELEGRAM_NATIVE:
        mp3_path = filepath.with_suffix(".mp3")
        _convert_to_mp3(str(filepath), str(mp3_path))
        os.unlink(filepath)
        filepath = mp3_path
        ext = ".mp3"

    # Measure actual quality from the downloaded file — more reliable than metadata
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
