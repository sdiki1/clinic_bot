from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.constants import PREMIUM_EMOJI_GIFT_ID, PREMIUM_EMOJI_TOOTH_ID, PREMIUM_EMOJI_WORLD_ID


def phone_request_keyboard(
    button_text: str = "Поделиться номером",
    input_placeholder: str = "Нажмите кнопку или введите номер вручную",
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=button_text,
                    request_contact=True,
                    icon_custom_emoji_id=PREMIUM_EMOJI_TOOTH_ID,
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=input_placeholder,
    )


def start_consent_keyboard(source: str, button_text: str = "Далее") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"start_continue:{source}",
                    style="primary",
                    icon_custom_emoji_id=PREMIUM_EMOJI_TOOTH_ID,
                )
            ]
        ]
    )


def loyalty_url_keyboard(
    loyalty_url: str,
    button_text: str = "Перейти в систему лояльности",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    url=loyalty_url,
                    style="success",
                    icon_custom_emoji_id=PREMIUM_EMOJI_GIFT_ID,
                )
            ]
        ]
    )


def actions_inline_keyboard(
    site_url: str,
    _loyalty_url: str,
    site_button_text: str = "Перейти на сайт",
    loyalty_button_text: str = "Система лояльности",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=site_button_text,
                    url=site_url,
                    style="primary",
                    icon_custom_emoji_id=PREMIUM_EMOJI_WORLD_ID,
                )
            ],
            [
                InlineKeyboardButton(
                    text=loyalty_button_text,
                    callback_data="open_loyalty",
                    style="success",
                    icon_custom_emoji_id=PREMIUM_EMOJI_GIFT_ID,
                )
            ],
        ]
    )
