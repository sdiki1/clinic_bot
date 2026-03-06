from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import (
    PREMIUM_EMOJI_BOOKS_ID,
    PREMIUM_EMOJI_GREETING_ID,
    PREMIUM_EMOJI_GIFT_ID,
    PREMIUM_EMOJI_TOOTH_ID,
    PREMIUM_EMOJI_WORLD_ID,
    SOURCE_UNKNOWN,
    premium_emoji_html,
)
from bot.keyboards import (
    actions_inline_keyboard,
    loyalty_url_keyboard,
    phone_request_keyboard,
    start_consent_keyboard,
)
from bot.loyalty_reminders import ensure_loyalty_reminder_schedule, mark_loyalty_opened
from bot.phone_utils import hash_phone, mask_phone, normalize_phone
from bot.repository import create_lead, get_user_by_telegram_id, set_user_phone, upsert_user
from bot.services import (
    build_loyalty_url,
    extract_source,
    guide_title,
    resolve_guide_path,
    resolve_start_document_paths,
    source_label,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)

EMOJI_GREETING = premium_emoji_html(PREMIUM_EMOJI_GREETING_ID, "👋")
EMOJI_BOOKS = premium_emoji_html(PREMIUM_EMOJI_BOOKS_ID, "📚")
EMOJI_WORLD = premium_emoji_html(PREMIUM_EMOJI_WORLD_ID, "🌐")
EMOJI_GIFT = premium_emoji_html(PREMIUM_EMOJI_GIFT_ID, "🎁")
EMOJI_TOOTH = premium_emoji_html(PREMIUM_EMOJI_TOOTH_ID, "🦷")


async def send_start_documents(message: Message, settings: Settings) -> None:
    for path in resolve_start_document_paths(settings):
        await message.answer_document(
            document=FSInputFile(path)
        )


async def send_links_menu(message: Message, settings: Settings) -> None:
    if message.from_user is None:
        return

    loyalty_url = build_loyalty_url(settings, message.from_user.id)
    keyboard = actions_inline_keyboard(settings.clinic_site_url, loyalty_url)
    await message.answer(
        f"{EMOJI_TOOTH} С возвращением!\n"
        f"{EMOJI_WORLD} Можете перейти на сайт клиники или в бонусную систему.\n"
        f"{EMOJI_GIFT} Нажмите «Мой бонусный счет», чтобы получить ссылку на переход.\n"
        "Если хотите снова получить гайд, используйте команду /guide.",
        reply_markup=keyboard,
    )


async def send_guide(message: Message, settings: Settings, source: str) -> None:
    if message.from_user is None:
        return

    loyalty_url = build_loyalty_url(settings, message.from_user.id)
    keyboard = actions_inline_keyboard(settings.clinic_site_url, loyalty_url)

    guide_path = resolve_guide_path(settings, source)
    title = guide_title(source)

    if guide_path is None:
        await message.answer(
            f"{EMOJI_BOOKS} Спасибо за заявку!\n"
            "Сейчас гайд временно недоступен, но вы уже можете перейти на сайт или в бонусную систему.",
            reply_markup=keyboard,
        )
        return

    await message.answer_document(
        document=FSInputFile(guide_path),
        caption=(
            f"{EMOJI_BOOKS} {title}\n"
            "Спасибо за заявку! Держите ваш гайд и полезные ссылки ниже."
        ),
        reply_markup=keyboard,
    )


async def notify_manager(
    bot: Bot,
    settings: Settings,
    *,
    first_name: str | None,
    username: str | None,
    telegram_id: int,
    phone: str,
    source: str,
) -> None:
    lead_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    username_line = f"@{username}" if username else "—"
    text = (
        "🚨 Новый лид\n"
        f"Имя: {first_name or '—'}\n"
        f"Username: {username_line}\n"
        f"Telegram ID: {telegram_id}\n"
        f"Телефон: {phone}\n"
        f"Источник: {source_label(source)}\n"
        f"Дата: {lead_time}"
    )

    try:
        await bot.send_message(chat_id=settings.manager_chat_id, text=text)
    except Exception:
        logger.exception("Failed to notify manager chat %s", settings.manager_chat_id)


async def process_phone_submission(
    message: Message,
    raw_phone: str,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    normalized_phone = normalize_phone(raw_phone)
    if not normalized_phone:
        await message.answer(
            "⚠️ Не получилось распознать номер.\n"
            "Пожалуйста, отправьте номер в формате +79991234567 или минимум 10 цифр.",
            reply_markup=phone_request_keyboard(),
        )
        return

    user = await upsert_user(session, message.from_user, source=None)
    if user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
        await session.commit()
        await message.answer("✅ Номер уже сохранен.", reply_markup=ReplyKeyboardRemove())
        await send_links_menu(message, settings)
        return

    phone_hash = hash_phone(normalized_phone, settings.phone_hash_salt)
    phone_masked = mask_phone(normalized_phone)
    set_user_phone(user, phone_hash=phone_hash, phone_masked=phone_masked)
    ensure_loyalty_reminder_schedule(user)
    create_lead(
        session,
        user=user,
        phone_hash=phone_hash,
        phone_masked=phone_masked,
        source=user.source or SOURCE_UNKNOWN,
    )
    await session.commit()

    await message.answer(
        "✅ Спасибо! Номер сохранен.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await send_guide(message, settings, user.source or SOURCE_UNKNOWN)
    await notify_manager(
        message.bot,
        settings,
        first_name=user.first_name,
        username=user.username,
        telegram_id=user.telegram_id,
        phone=normalized_phone,
        source=user.source or SOURCE_UNKNOWN,
    )


async def continue_start_flow(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    source: str,
) -> None:
    if message.from_user is None:
        return

    user = await upsert_user(session, message.from_user, source=source)
    if user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
    await session.commit()

    if user.phone_hash:
        await message.answer(f"{EMOJI_GREETING} Вы уже зарегистрированы.", reply_markup=ReplyKeyboardRemove())
        await send_links_menu(message, settings)
        return

    await message.answer(
        f"{EMOJI_GREETING} Привет! Я бот клиники MARULIDI.\n"
        f"{EMOJI_BOOKS} Чтобы получить полезный PDF-гайд, поделитесь номером телефона.",
        reply_markup=phone_request_keyboard(),
    )


@router.message(CommandStart())
async def on_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    source = extract_source(command.args)
    user = await upsert_user(session, message.from_user, source=source)
    if user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
    await session.commit()

    if user.phone_hash:
        await message.answer(f"{EMOJI_GREETING} Вы уже зарегистрированы.", reply_markup=ReplyKeyboardRemove())
        await send_links_menu(message, settings)
        return

    await send_start_documents(message, settings)
    await message.answer(
        "Нажимая кнопку «Далее», Вы соглашаетесь с:\n• Политикой обработки персональных данных\n• Получением информационно-рекламных сообщений",
        reply_markup=start_consent_keyboard(source),
    )


@router.callback_query(F.data.startswith("start_continue:"))
async def on_start_continue(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    data = callback.data or ""
    source = extract_source(data.split(":", maxsplit=1)[1] if ":" in data else None)

    await callback.answer()

    if not isinstance(callback.message, Message):
        return

    with suppress(Exception):
        await callback.message.edit_reply_markup(reply_markup=None)

    await continue_start_flow(
        callback.message,
        session,
        settings,
        source,
    )


@router.callback_query(F.data == "open_loyalty")
async def on_open_loyalty(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None:
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if user is not None:
        mark_loyalty_opened(user)
        await session.commit()

    await callback.answer("Отправил ссылку на бонусную систему")

    if not isinstance(callback.message, Message):
        return

    loyalty_url = build_loyalty_url(settings, callback.from_user.id)
    await callback.message.answer(
        f"{EMOJI_GIFT} Перейти в бонусную систему:\n{loyalty_url}",
        reply_markup=loyalty_url_keyboard(loyalty_url),
    )


@router.message(Command("guide"))
async def on_guide(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user is None or user.phone_hash is None:
        await message.answer(
            "📞 Сначала поделитесь номером телефона, чтобы получить гайд.",
            reply_markup=phone_request_keyboard(),
        )
        return

    ensure_loyalty_reminder_schedule(user)
    await session.commit()
    await send_guide(message, settings, user.source or SOURCE_UNKNOWN)


@router.message(F.contact)
async def on_contact(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.contact is None or message.from_user is None:
        return

    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ Отправьте, пожалуйста, свой номер через кнопку ниже.",
            reply_markup=phone_request_keyboard(),
        )
        return

    await process_phone_submission(message, message.contact.phone_number, session, settings)


@router.message(F.text)
async def on_text_phone_fallback(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None or not message.text:
        return

    if message.text.startswith("/"):
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user and user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
        await session.commit()
        await send_links_menu(message, settings)
        return

    await process_phone_submission(message, message.text, session, settings)
