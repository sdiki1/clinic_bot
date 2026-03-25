from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bot.bot_texts import get_bot_text_values, render_bot_text
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
from bot.models import User
from bot.phone_utils import hash_phone, mask_phone, normalize_phone
from bot.repository import create_lead, get_user_by_telegram_id, set_user_phone, upsert_user
from bot.services import (
    build_loyalty_url,
    extract_source,
    normalize_source_key,
    resolve_guide_delivery_config,
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
NEW_USER_NOTIFICATION_CHAT_ID = 1077175363


async def _resolve_bot_texts(
    session: AsyncSession,
    current: dict[str, str] | None = None,
) -> dict[str, str]:
    if current is not None:
        return current
    return await get_bot_text_values(session)


async def send_start_documents(message: Message, settings: Settings) -> None:
    for path in resolve_start_document_paths(settings):
        await message.answer_document(
            document=FSInputFile(path)
        )


async def send_links_menu(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    source: str,
    bot_texts: dict[str, str] | None = None,
) -> None:
    if message.from_user is None:
        return

    texts = await _resolve_bot_texts(session, bot_texts)
    loyalty_url = build_loyalty_url(settings, message.from_user.id)
    guide_config = await resolve_guide_delivery_config(session, settings, source)
    keyboard = actions_inline_keyboard(
        guide_config.button_url,
        loyalty_url,
        site_button_text=guide_config.button_text,
        loyalty_button_text=texts["actions_loyalty_button_text"],
    )
    links_menu_message = render_bot_text(
        texts["links_menu_message"],
        emoji_tooth=EMOJI_TOOTH,
        emoji_world=EMOJI_WORLD,
        emoji_gift=EMOJI_GIFT,
    )
    await message.answer(
        links_menu_message,
        reply_markup=keyboard,
    )


async def send_guide(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    source: str,
    bot_texts: dict[str, str] | None = None,
) -> None:
    if message.from_user is None:
        return

    texts = await _resolve_bot_texts(session, bot_texts)
    guide_config = await resolve_guide_delivery_config(session, settings, source)
    loyalty_url = build_loyalty_url(settings, message.from_user.id)
    keyboard = actions_inline_keyboard(
        guide_config.button_url,
        loyalty_url,
        site_button_text=guide_config.button_text,
        loyalty_button_text=texts["actions_loyalty_button_text"],
    )

    if guide_config.pdf_path is None:
        await message.answer(
            render_bot_text(texts["guide_unavailable_message"], emoji_books=EMOJI_BOOKS),
            reply_markup=keyboard,
        )
        return

    caption = guide_config.message_text.strip()
    if len(caption) > 1024:
        caption = caption[:1021].rstrip() + "..."

    await message.answer_document(
        document=FSInputFile(guide_config.pdf_path),
        caption=caption,
        reply_markup=keyboard,
        parse_mode=None,
    )


async def notify_manager(
    bot: Bot,
    settings: Settings,
    *,
    template_text: str,
    first_name: str | None,
    username: str | None,
    telegram_id: int,
    phone: str,
    source: str,
) -> None:
    lead_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    username_line = f"@{username}" if username else "—"
    text = render_bot_text(
        template_text,
        first_name=first_name or "—",
        username_line=username_line,
        telegram_id=telegram_id,
        phone=phone,
        source=source_label(source),
        lead_time=lead_time,
    )

    try:
        await bot.send_message(chat_id=settings.manager_chat_id, text=text)
    except Exception:
        logger.exception("Failed to notify manager chat %s", settings.manager_chat_id)


def format_new_user_notification_text(
    *,
    template_text: str,
    registered_at: datetime | None,
    first_name: str | None,
    username: str | None,
    telegram_id: int,
    phone: str | None,
    source: str,
) -> str:
    if registered_at is None:
        normalized_registered_at = datetime.now(timezone.utc)
    elif registered_at.tzinfo is None:
        normalized_registered_at = registered_at.replace(tzinfo=timezone.utc)
    else:
        normalized_registered_at = registered_at.astimezone(timezone.utc)

    registered_at_text = normalized_registered_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    username_line = f"@{username}" if username else "—"
    return render_bot_text(
        template_text,
        registered_at=registered_at_text,
        first_name=first_name or "—",
        username_line=username_line,
        telegram_id=telegram_id,
        phone=phone or "—",
        source=source_label(source),
    )


async def notify_new_user(
    bot: Bot,
    *,
    template_text: str,
    registered_at: datetime | None,
    first_name: str | None,
    username: str | None,
    telegram_id: int,
    phone: str | None,
    source: str,
) -> int | None:
    text = format_new_user_notification_text(
        template_text=template_text,
        registered_at=registered_at,
        first_name=first_name,
        username=username,
        telegram_id=telegram_id,
        phone=phone,
        source=source,
    )

    try:
        sent_message = await bot.send_message(chat_id=NEW_USER_NOTIFICATION_CHAT_ID, text=text)
        return sent_message.message_id
    except Exception:
        logger.exception(
            "Failed to notify new user chat %s",
            NEW_USER_NOTIFICATION_CHAT_ID,
        )
        return None


async def edit_new_user_notification_phone(
    bot: Bot,
    *,
    template_text: str,
    notification_message_id: int | None,
    registered_at: datetime | None,
    first_name: str | None,
    username: str | None,
    telegram_id: int,
    phone: str,
    source: str,
) -> None:
    if notification_message_id is None:
        return

    text = format_new_user_notification_text(
        template_text=template_text,
        registered_at=registered_at,
        first_name=first_name,
        username=username,
        telegram_id=telegram_id,
        phone=phone,
        source=source,
    )

    try:
        await bot.edit_message_text(
            chat_id=NEW_USER_NOTIFICATION_CHAT_ID,
            message_id=notification_message_id,
            text=text,
        )
    except Exception:
        logger.exception(
            "Failed to edit new user notification message %s in chat %s",
            notification_message_id,
            NEW_USER_NOTIFICATION_CHAT_ID,
        )


async def send_new_user_notification_if_needed(
    session: AsyncSession,
    bot: Bot,
    *,
    user: User,
    is_new_user: bool,
    phone: str | None = None,
    bot_texts: dict[str, str] | None = None,
) -> None:
    if not is_new_user:
        return

    texts = await _resolve_bot_texts(session, bot_texts)
    notification_message_id = await notify_new_user(
        bot,
        template_text=texts["new_user_notification_template"],
        registered_at=user.reg_date,
        first_name=user.first_name,
        username=user.username,
        telegram_id=user.telegram_id,
        phone=phone or user.phone_masked,
        source=user.source or SOURCE_UNKNOWN,
    )
    if notification_message_id is None:
        return

    user.new_user_notification_message_id = notification_message_id
    await session.commit()


async def process_phone_submission(
    message: Message,
    raw_phone: str,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    texts = await get_bot_text_values(session)
    normalized_phone = normalize_phone(raw_phone)
    if not normalized_phone:
        await message.answer(
            texts["phone_parse_error_message"],
            reply_markup=phone_request_keyboard(
                button_text=texts["phone_request_button_text"],
                input_placeholder=texts["phone_request_input_placeholder"],
            ),
        )
        return

    user, is_new_user = await upsert_user(session, message.from_user, source=None)
    if user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
        await session.commit()
        await message.answer(texts["phone_already_saved_message"], reply_markup=ReplyKeyboardRemove())
        await send_links_menu(
            message,
            session,
            settings,
            user.source or SOURCE_UNKNOWN,
            bot_texts=texts,
        )
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
    if is_new_user:
        await send_new_user_notification_if_needed(
            session,
            message.bot,
            user=user,
            is_new_user=is_new_user,
            phone=normalized_phone,
            bot_texts=texts,
        )
    else:
        await notify_new_user(
            message.bot,
            template_text=texts["new_user_notification_template"],
            registered_at=user.reg_date,
            first_name=user.first_name,
            username=user.username,
            telegram_id=user.telegram_id,
            phone=normalized_phone,
            source=user.source or SOURCE_UNKNOWN,
        )

    await message.answer(
        texts["phone_saved_message"],
        reply_markup=ReplyKeyboardRemove(),
    )
    await send_guide(
        message,
        session,
        settings,
        user.source or SOURCE_UNKNOWN,
        bot_texts=texts,
    )
    await notify_manager(
        message.bot,
        settings,
        template_text=texts["manager_notification_template"],
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

    texts = await get_bot_text_values(session)
    user, is_new_user = await upsert_user(session, message.from_user, source=source)
    if user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
    await session.commit()
    await send_new_user_notification_if_needed(
        session,
        message.bot,
        user=user,
        is_new_user=is_new_user,
        bot_texts=texts,
    )

    if user.phone_hash:
        await message.answer(
            render_bot_text(texts["already_registered_message"], emoji_greeting=EMOJI_GREETING),
            reply_markup=ReplyKeyboardRemove(),
        )
        if source != SOURCE_UNKNOWN:
            await send_guide(message, session, settings, source, bot_texts=texts)
        else:
            await send_links_menu(
                message,
                session,
                settings,
                user.source or SOURCE_UNKNOWN,
                bot_texts=texts,
            )
        return

    guide_config = await resolve_guide_delivery_config(session, settings, source)
    await message.answer(
        guide_config.intro_message_text,
        reply_markup=phone_request_keyboard(
            button_text=texts["phone_request_button_text"],
            input_placeholder=texts["phone_request_input_placeholder"],
        ),
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

    texts = await get_bot_text_values(session)
    start_arg = command.args
    source = extract_source(start_arg)
    has_deep_link = normalize_source_key(start_arg) not in {None, SOURCE_UNKNOWN}
    user, is_new_user = await upsert_user(session, message.from_user, source=source)
    if user.phone_hash:
        ensure_loyalty_reminder_schedule(user)
    await session.commit()
    await send_new_user_notification_if_needed(
        session,
        message.bot,
        user=user,
        is_new_user=is_new_user,
        bot_texts=texts,
    )

    if user.phone_hash:
        await message.answer(
            render_bot_text(texts["already_registered_message"], emoji_greeting=EMOJI_GREETING),
            reply_markup=ReplyKeyboardRemove(),
        )
        if has_deep_link:
            await send_guide(message, session, settings, source, bot_texts=texts)
        else:
            await send_links_menu(
                message,
                session,
                settings,
                user.source or SOURCE_UNKNOWN,
                bot_texts=texts,
            )
        return

    await send_start_documents(message, settings)
    await message.answer(
        texts["consent_message"],
        reply_markup=start_consent_keyboard(source, button_text=texts["start_continue_button_text"]),
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

    texts = await get_bot_text_values(session)
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if user is not None:
        mark_loyalty_opened(user)
        await session.commit()

    await callback.answer(texts["loyalty_link_toast"])

    if not isinstance(callback.message, Message):
        return

    loyalty_url = build_loyalty_url(settings, callback.from_user.id)
    await callback.message.answer(
        render_bot_text(
            texts["loyalty_link_message"],
            emoji_gift=EMOJI_GIFT,
            loyalty_url=loyalty_url,
        ),
        reply_markup=loyalty_url_keyboard(
            loyalty_url,
            button_text=texts["loyalty_open_button_text"],
        ),
    )


@router.message(Command("guide"))
async def on_guide(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    texts = await get_bot_text_values(session)
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user is None or user.phone_hash is None:
        await message.answer(
            texts["guide_requires_phone_message"],
            reply_markup=phone_request_keyboard(
                button_text=texts["phone_request_button_text"],
                input_placeholder=texts["phone_request_input_placeholder"],
            ),
        )
        return

    ensure_loyalty_reminder_schedule(user)
    await session.commit()
    await send_guide(
        message,
        session,
        settings,
        user.source or SOURCE_UNKNOWN,
        bot_texts=texts,
    )


@router.message(F.contact)
async def on_contact(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.contact is None or message.from_user is None:
        return

    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        texts = await get_bot_text_values(session)
        await message.answer(
            texts["send_own_phone_message"],
            reply_markup=phone_request_keyboard(
                button_text=texts["phone_request_button_text"],
                input_placeholder=texts["phone_request_input_placeholder"],
            ),
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
        texts = await get_bot_text_values(session)
        ensure_loyalty_reminder_schedule(user)
        await session.commit()
        await send_links_menu(
            message,
            session,
            settings,
            user.source or SOURCE_UNKNOWN,
            bot_texts=texts,
        )
        return

    await process_phone_submission(message, message.text, session, settings)
