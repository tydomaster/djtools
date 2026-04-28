import os
from dataclasses import dataclass, field


def _parse_admin_ids() -> list[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    return [int(p.strip()) for p in raw.split(",") if p.strip().isdigit()]


@dataclass
class Settings:
    bot_token: str = field(default_factory=lambda: os.environ["BOT_TOKEN"])
    admin_ids: list[int] = field(default_factory=_parse_admin_ids)

    # Auth for 320 kbps SoundCloud Go+ quality.
    # Preferred: base64-encoded Netscape cookies.txt (lasts 6-12 months).
    # Fallback: raw OAuth token from DevTools (lasts months but shorter).
    soundcloud_cookies: str = field(
        default_factory=lambda: os.environ.get("SOUNDCLOUD_COOKIES", "")
    )
    soundcloud_oauth_token: str = field(
        default_factory=lambda: os.environ.get("SOUNDCLOUD_OAUTH_TOKEN", "")
    )

    # Concurrency / rate limiting (tunable per Railway plan)
    max_concurrent_downloads: int = field(
        default_factory=lambda: int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))
    )
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.environ.get("CACHE_TTL_SECONDS", "3600"))
    )
    rate_limit_max: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_MAX", "10"))
    )
    rate_limit_window: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_WINDOW", "3600"))
    )


settings = Settings()
