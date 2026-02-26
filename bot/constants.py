from __future__ import annotations

from typing import Final

SOURCE_INSTAGRAM: Final[str] = "instagram"
SOURCE_YOUTUBE: Final[str] = "youtube"
SOURCE_SITE: Final[str] = "site"
SOURCE_UNKNOWN: Final[str] = "unknown"

PREMIUM_EMOJI_GREETING_ID: Final[str] = "5472055112702629499"
PREMIUM_EMOJI_BOOKS_ID: Final[str] = "5373098009640836781"
PREMIUM_EMOJI_WORLD_ID: Final[str] = "5821388137443626414"
PREMIUM_EMOJI_GIFT_ID: Final[str] = "5203996991054432397"
PREMIUM_EMOJI_TOOTH_ID: Final[str] = "5469760204302196866"

KNOWN_SOURCES: Final[set[str]] = {
    SOURCE_INSTAGRAM,
    SOURCE_YOUTUBE,
    SOURCE_SITE,
}

SOURCE_LABELS: Final[dict[str, str]] = {
    SOURCE_INSTAGRAM: "Instagram",
    SOURCE_YOUTUBE: "YouTube",
    SOURCE_SITE: "Сайт/другой канал",
    SOURCE_UNKNOWN: "Не определен",
}

GUIDE_TITLES: Final[dict[str, str]] = {
    SOURCE_INSTAGRAM: "Instagram Гайд: Как сохранить улыбку",
    SOURCE_YOUTUBE: "YouTube Гайд: Топ-5 процедур",
    SOURCE_SITE: "Универсальный гайд по уходу за улыбкой",
    SOURCE_UNKNOWN: "Универсальный гайд по уходу за улыбкой",
}


def premium_emoji_html(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
