from datetime import datetime, timezone

from bot.loyalty_reminders import (
    FIRST_REMINDER_DELAY,
    REPEAT_REMINDER_DELAY,
    SECOND_REMINDER_DELAY,
    ensure_loyalty_reminder_schedule,
    mark_loyalty_opened,
    next_delay_after_send,
    reminder_text_for_attempt,
)
from bot.models import LoyaltyReminderConfig, User


def test_reminder_text_for_attempt() -> None:
    config = LoyaltyReminderConfig(
        id=1,
        message_24h="24h",
        message_5d="5d",
        message_7d="7d",
    )
    assert reminder_text_for_attempt(config, 0) == "24h"
    assert reminder_text_for_attempt(config, 1) == "5d"
    assert reminder_text_for_attempt(config, 2) == "7d"


def test_next_delay_after_send() -> None:
    assert next_delay_after_send(0) == SECOND_REMINDER_DELAY
    assert next_delay_after_send(1) == REPEAT_REMINDER_DELAY
    assert next_delay_after_send(5) == REPEAT_REMINDER_DELAY


def test_ensure_loyalty_reminder_schedule() -> None:
    now = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
    user = User(telegram_id=100, source="unknown")

    ensure_loyalty_reminder_schedule(user, now)

    assert user.loyalty_reminder_sent_count == 0
    assert user.loyalty_reminder_next_at == now + FIRST_REMINDER_DELAY


def test_mark_loyalty_opened_stops_schedule() -> None:
    now = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
    user = User(telegram_id=100, source="unknown")
    ensure_loyalty_reminder_schedule(user, now)

    mark_loyalty_opened(user, now)

    assert user.loyalty_opened_at == now
    assert user.loyalty_reminder_next_at is None
