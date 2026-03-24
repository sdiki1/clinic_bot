from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import (
    GUIDE_TITLES,
    SOURCE_INSTAGRAM,
    SOURCE_SITE,
    SOURCE_YOUTUBE,
    SOURCE_LABELS,
    SOURCE_UNKNOWN,
)
from bot.models import GuideLink

SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class GuideDeliveryConfig:
    source: str
    name: str
    intro_message_text: str
    message_text: str
    button_text: str
    button_url: str
    pdf_path: Path | None


def normalize_source_key(source: str | None) -> str | None:
    if source is None:
        return None
    candidate = source.strip().lower()
    if not candidate:
        return None
    if SOURCE_KEY_RE.fullmatch(candidate):
        return candidate
    return None


def default_guide_message(title: str) -> str:
    return (
        f"📚 {title}\n"
        "Спасибо за заявку! Держите ваш гайд и полезные ссылки ниже."
    )


def default_intro_message(title: str) -> str:
    return (
        f"👋 Привет! Я бот клиники MARULIDI.\n"
        f"📄 Чтобы получить материал «{title}», поделитесь номером телефона."
    )


def normalize_public_url(url: str | None) -> str | None:
    if url is None:
        return None
    candidate = url.strip()
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def extract_source(start_arg: str | None) -> str:
    return normalize_source_key(start_arg) or SOURCE_UNKNOWN


def source_label(source: str | None) -> str:
    if not source:
        return SOURCE_LABELS[SOURCE_UNKNOWN]
    normalized = normalize_source_key(source) or source.strip().lower()
    return SOURCE_LABELS.get(normalized, normalized)


def guide_title(source: str | None) -> str:
    if not source:
        return GUIDE_TITLES[SOURCE_UNKNOWN]
    normalized = normalize_source_key(source) or source.strip().lower()
    return GUIDE_TITLES.get(normalized, GUIDE_TITLES[SOURCE_UNKNOWN])


def build_loyalty_url(settings: Settings, telegram_id: int) -> str:
    payload = f"{settings.loyalty_start_prefix}{telegram_id}"
    return f"https://t.me/{settings.loyalty_bot_username}?start={payload}"


def build_start_deep_link(settings: Settings, source: str) -> str:
    bot_username = settings.bot_username.strip()
    if not bot_username:
        return f"?start={source}"
    return f"https://t.me/{bot_username}?start={source}"


def guide_pdf_storage_path(settings: Settings, source: str) -> Path:
    normalized_source = normalize_source_key(source) or SOURCE_SITE
    return settings.guide_links_dir / f"{normalized_source}.pdf"


def default_guide_link_definitions(settings: Settings) -> list[dict[str, str | None]]:
    return [
        {
            "source": SOURCE_INSTAGRAM,
            "name": "Instagram Гайд",
            "intro_message_text": default_intro_message("Instagram Гайд"),
            "pdf_path": str(settings.guide_instagram_path) if settings.guide_instagram_path else None,
        },
        {
            "source": SOURCE_YOUTUBE,
            "name": "YouTube Гайд",
            "intro_message_text": default_intro_message("YouTube Гайд"),
            "pdf_path": str(settings.guide_youtube_path) if settings.guide_youtube_path else None,
        },
        {
            "source": SOURCE_SITE,
            "name": "Универсальный Гайд",
            "intro_message_text": default_intro_message("Универсальный Гайд"),
            "pdf_path": str(settings.guide_default_path) if settings.guide_default_path else None,
        },
    ]


async def ensure_default_guide_links(session: AsyncSession, settings: Settings) -> bool:
    existing = (await session.scalars(select(GuideLink))).all()
    if existing:
        return False

    for item in default_guide_link_definitions(settings):
        source = str(item["source"])
        title = guide_title(source)
        session.add(
            GuideLink(
                source=source,
                name=str(item["name"]),
                intro_message_text=str(item["intro_message_text"]),
                message_text=default_guide_message(title),
                button_text="Перейти на сайт",
                button_url=settings.clinic_site_url,
                pdf_path=item["pdf_path"],
            )
        )
    await session.flush()
    return True


def _guide_link_to_delivery_config(settings: Settings, link: GuideLink) -> GuideDeliveryConfig:
    name = link.name.strip() if link.name else source_label(link.source)
    intro_message_text = (link.intro_message_text or "").strip() or default_intro_message(name)
    message_text = (link.message_text or "").strip() or default_guide_message(name)
    button_text = (link.button_text or "").strip() or "Перейти на сайт"
    button_url = normalize_public_url(link.button_url) or settings.clinic_site_url

    path_text = (link.pdf_path or "").strip()
    pdf_path = Path(path_text) if path_text else guide_pdf_storage_path(settings, link.source)
    if not pdf_path.exists():
        pdf_path = None

    return GuideDeliveryConfig(
        source=link.source,
        name=name,
        intro_message_text=intro_message_text,
        message_text=message_text,
        button_text=button_text,
        button_url=button_url,
        pdf_path=pdf_path,
    )


async def resolve_guide_delivery_config(
    session: AsyncSession,
    settings: Settings,
    source: str | None,
) -> GuideDeliveryConfig:
    normalized_source = extract_source(source)
    candidate_sources: list[str] = []
    if normalized_source != SOURCE_UNKNOWN:
        candidate_sources.append(normalized_source)
    if SOURCE_SITE not in candidate_sources:
        candidate_sources.append(SOURCE_SITE)

    rows = (
        await session.scalars(
            select(GuideLink).where(GuideLink.source.in_(candidate_sources))
        )
    ).all()
    rows_map = {row.source: row for row in rows}

    for candidate in candidate_sources:
        link = rows_map.get(candidate)
        if link is not None:
            return _guide_link_to_delivery_config(settings, link)

    legacy_path = resolve_guide_path(settings, normalized_source)
    title = guide_title(normalized_source)
    return GuideDeliveryConfig(
        source=normalized_source,
        name=title,
        intro_message_text=default_intro_message(title),
        message_text=default_guide_message(title),
        button_text="Перейти на сайт",
        button_url=settings.clinic_site_url,
        pdf_path=legacy_path,
    )


def resolve_guide_path(settings: Settings, source: str | None) -> Path | None:
    source_map = {
        SOURCE_INSTAGRAM: settings.guide_instagram_path,
        SOURCE_YOUTUBE: settings.guide_youtube_path,
        SOURCE_SITE: settings.guide_default_path,
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
