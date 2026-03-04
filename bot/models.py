from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.constants import SOURCE_UNKNOWN
from bot.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    phone_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False, default=SOURCE_UNKNOWN)
    loyalty_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loyalty_reminder_sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loyalty_reminder_next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loyalty_reminder_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reg_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(32), nullable=False)

    source: Mapped[str] = mapped_column(String(32), nullable=False, default=SOURCE_UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class LoyaltyReminderConfig(Base):
    __tablename__ = "loyalty_reminder_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    message_24h: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=(
            "Вы еще не активировали бонусный счет.\n"
            "Нажмите кнопку «Мой бонусный счет», чтобы перейти в систему лояльности."
        ),
    )
    message_5d: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=(
            "Напоминаем: бонусный счет все еще не активирован.\n"
            "Перейдите в систему лояльности — это займет меньше минуты."
        ),
    )
    message_7d: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=(
            "Бонусный счет все еще ждет активации.\n"
            "Нажмите «Мой бонусный счет» и завершите переход в систему лояльности."
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
