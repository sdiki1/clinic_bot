from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.constants import PREMIUM_EMOJI_GIFT_ID, PREMIUM_EMOJI_TOOTH_ID, PREMIUM_EMOJI_WORLD_ID


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Поделиться номером",
                    request_contact=True,
                    icon_custom_emoji_id=PREMIUM_EMOJI_TOOTH_ID,
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Нажмите кнопку или введите номер вручную",
    )


def start_consent_keyboard(source: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Далее",
                    callback_data=f"start_continue:{source}",
                    style="primary",
                    icon_custom_emoji_id=PREMIUM_EMOJI_TOOTH_ID,
                )
            ]
        ]
    )


def loyalty_url_keyboard(loyalty_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перейти в бонусную систему",
                    url=loyalty_url,
                    style="success",
                    icon_custom_emoji_id=PREMIUM_EMOJI_GIFT_ID,
                )
            ]
        ]
    )


def actions_inline_keyboard(site_url: str, _loyalty_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перейти на сайт",
                    url=site_url,
                    style="primary",
                    icon_custom_emoji_id=PREMIUM_EMOJI_WORLD_ID,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Мой бонусный счет",
                    callback_data="open_loyalty",
                    style="success",
                    icon_custom_emoji_id=PREMIUM_EMOJI_GIFT_ID,
                )
            ],
        ]
    )
