import os
from dataclasses import dataclass, field


def _parse_admin_ids() -> list[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


@dataclass
class Settings:
    bot_token: str = field(default_factory=lambda: os.environ["BOT_TOKEN"])
    admin_ids: list[int] = field(default_factory=_parse_admin_ids)


settings = Settings()
