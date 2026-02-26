from __future__ import annotations

from typing import Final

SOURCE_INSTAGRAM: Final[str] = "instagram"
SOURCE_YOUTUBE: Final[str] = "youtube"
SOURCE_SITE: Final[str] = "site"
SOURCE_UNKNOWN: Final[str] = "unknown"

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
