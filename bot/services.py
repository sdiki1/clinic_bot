from __future__ import annotations

from pathlib import Path

from bot.config import Settings
from bot.constants import (
    GUIDE_TITLES,
    KNOWN_SOURCES,
    SOURCE_LABELS,
    SOURCE_UNKNOWN,
)


def extract_source(start_arg: str | None) -> str:
    if not start_arg:
        return SOURCE_UNKNOWN
    candidate = start_arg.strip().lower()
    if candidate in KNOWN_SOURCES:
        return candidate
    return SOURCE_UNKNOWN


def source_label(source: str | None) -> str:
    if not source:
        return SOURCE_LABELS[SOURCE_UNKNOWN]
    return SOURCE_LABELS.get(source, SOURCE_LABELS[SOURCE_UNKNOWN])


def guide_title(source: str | None) -> str:
    if not source:
        return GUIDE_TITLES[SOURCE_UNKNOWN]
    return GUIDE_TITLES.get(source, GUIDE_TITLES[SOURCE_UNKNOWN])


def build_loyalty_url(settings: Settings, telegram_id: int) -> str:
    payload = f"{settings.loyalty_start_prefix}{telegram_id}"
    return f"https://t.me/{settings.loyalty_bot_username}?start={payload}"


def resolve_guide_path(settings: Settings, source: str | None) -> Path | None:
    source_map = {
        "instagram": settings.guide_instagram_path,
        "youtube": settings.guide_youtube_path,
        "site": settings.guide_default_path,
        SOURCE_UNKNOWN: settings.guide_default_path,
    }

    selected = source_map.get(source or SOURCE_UNKNOWN)
    if selected and selected.exists():
        return selected

    fallbacks = [
        settings.guide_default_path,
        settings.guide_instagram_path,
        settings.guide_youtube_path,
    ]
    for candidate in fallbacks:
        if candidate and candidate.exists():
            return candidate

    return None


def resolve_start_document_paths(settings: Settings, *, max_files: int = 7) -> list[Path]:
    docs_dir = settings.start_documents_dir
    files_from_dir: list[Path] = []
    if docs_dir.exists() and docs_dir.is_dir():
        files_from_dir = sorted(
            [
                path
                for path in docs_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".pdf"
            ],
            key=lambda path: path.name.lower(),
        )

    if files_from_dir:
        return files_from_dir[:max_files]

    fallback = [
        settings.start_terms_path,
        settings.start_privacy_path,
    ]
    return [path for path in fallback if path and path.exists()][:max_files]
