from __future__ import annotations

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import SOURCE_UNKNOWN
from bot.models import Lead, User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    return await session.scalar(stmt)


async def upsert_user(
    session: AsyncSession,
    tg_user: TgUser,
    source: str | None,
) -> tuple[User, bool]:
    user = await get_user_by_telegram_id(session, tg_user.id)
    normalized_source = source or SOURCE_UNKNOWN

    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            source=normalized_source,
        )
        session.add(user)
        await session.flush()
        return user, True

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    if normalized_source != SOURCE_UNKNOWN:
        user.source = normalized_source

    return user, False


def set_user_phone(user: User, phone_hash: str, phone_masked: str) -> None:
    user.phone_hash = phone_hash
    user.phone_masked = phone_masked


def create_lead(
    session: AsyncSession,
    user: User,
    phone_hash: str,
    phone_masked: str,
    source: str,
) -> Lead:
    lead = Lead(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        phone_hash=phone_hash,
        phone_masked=phone_masked,
        source=source,
    )
    session.add(lead)
    return lead
