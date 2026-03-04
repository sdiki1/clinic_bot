from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.keyboards import actions_inline_keyboard
from bot.models import LoyaltyReminderConfig, User, utcnow
from bot.services import build_loyalty_url

logger = logging.getLogger(__name__)

FIRST_REMINDER_DELAY = timedelta(hours=24)
SECOND_REMINDER_DELAY = timedelta(days=5)
REPEAT_REMINDER_DELAY = timedelta(days=7)


def reminder_text_for_attempt(config: LoyaltyReminderConfig, sent_count_before: int) -> str:
    if sent_count_before <= 0:
        return config.message_24h
    if sent_count_before == 1:
        return config.message_5d
    return config.message_7d


def next_delay_after_send(sent_count_before: int) -> timedelta:
    if sent_count_before <= 0:
        return SECOND_REMINDER_DELAY
    return REPEAT_REMINDER_DELAY


def ensure_loyalty_reminder_schedule(user: User, now: datetime | None = None) -> None:
    if user.loyalty_opened_at is not None:
        user.loyalty_reminder_next_at = None
        return
    if user.loyalty_reminder_next_at is not None:
        return

    now_utc = now or utcnow()
    user.loyalty_reminder_sent_count = user.loyalty_reminder_sent_count or 0
    user.loyalty_reminder_next_at = now_utc + FIRST_REMINDER_DELAY


def mark_loyalty_opened(user: User, now: datetime | None = None) -> None:
    now_utc = now or utcnow()
    user.loyalty_opened_at = now_utc
    user.loyalty_reminder_next_at = None


async def get_or_create_reminder_config(session: AsyncSession) -> LoyaltyReminderConfig:
    config = await session.get(LoyaltyReminderConfig, 1)
    if config is not None:
        return config

    config = LoyaltyReminderConfig(id=1)
    session.add(config)
    await session.flush()
    return config


async def bootstrap_loyalty_reminder_schedule(
    session: AsyncSession,
    *,
    batch_size: int,
    now: datetime | None = None,
) -> int:
    now_utc = now or utcnow()
    users = (
        await session.scalars(
            select(User)
            .where(User.phone_hash.is_not(None))
            .where(User.loyalty_opened_at.is_(None))
            .where(User.loyalty_reminder_next_at.is_(None))
            .limit(batch_size)
        )
    ).all()

    for user in users:
        ensure_loyalty_reminder_schedule(user, now_utc)

    return len(users)


async def process_loyalty_reminders(bot: Bot, session: AsyncSession, settings: Settings) -> int:
    config = await get_or_create_reminder_config(session)
    now = utcnow()

    # Backfill schedule for users created before this feature.
    await bootstrap_loyalty_reminder_schedule(
        session,
        batch_size=settings.loyalty_reminder_batch_size,
        now=now,
    )

    if not config.enabled:
        await session.commit()
        return 0

    due_users = (
        await session.scalars(
            select(User)
            .where(User.phone_hash.is_not(None))
            .where(User.loyalty_opened_at.is_(None))
            .where(User.loyalty_reminder_next_at.is_not(None))
            .where(User.loyalty_reminder_next_at <= now)
            .order_by(User.loyalty_reminder_next_at.asc())
            .limit(settings.loyalty_reminder_batch_size)
        )
    ).all()

    sent_count = 0
    for user in due_users:
        sent_count_before = user.loyalty_reminder_sent_count or 0
        message_text = reminder_text_for_attempt(config, sent_count_before).strip()
        if not message_text:
            user.loyalty_reminder_next_at = now + next_delay_after_send(sent_count_before)
            continue

        loyalty_url = build_loyalty_url(settings, user.telegram_id)
        keyboard = actions_inline_keyboard(settings.clinic_site_url, loyalty_url)

        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception("Failed to send loyalty reminder to user %s", user.telegram_id)
            # Avoid tight retry loops on send errors.
            user.loyalty_reminder_next_at = now + timedelta(hours=6)
            continue

        user.loyalty_reminder_sent_count = sent_count_before + 1
        user.loyalty_reminder_last_sent_at = now
        user.loyalty_reminder_next_at = now + next_delay_after_send(sent_count_before)
        sent_count += 1

    await session.commit()
    return sent_count


async def run_loyalty_reminder_loop(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    poll_seconds = max(settings.loyalty_reminder_poll_seconds, 15)
    while True:
        try:
            async with session_pool() as session:
                await process_loyalty_reminders(bot, session, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Loyalty reminder loop iteration failed")

        await asyncio.sleep(poll_seconds)
