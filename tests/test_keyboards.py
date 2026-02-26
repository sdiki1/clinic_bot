from bot.constants import PREMIUM_EMOJI_GIFT_ID, PREMIUM_EMOJI_TOOTH_ID, PREMIUM_EMOJI_WORLD_ID
from bot.keyboards import actions_inline_keyboard, phone_request_keyboard


def test_actions_inline_keyboard_styles_and_icons() -> None:
    kb = actions_inline_keyboard("https://example.com", "https://t.me/bonus_bot")

    site_btn = kb.inline_keyboard[0][0]
    loyalty_btn = kb.inline_keyboard[1][0]

    assert site_btn.style == "primary"
    assert site_btn.icon_custom_emoji_id == PREMIUM_EMOJI_WORLD_ID

    assert loyalty_btn.style == "success"
    assert loyalty_btn.icon_custom_emoji_id == PREMIUM_EMOJI_GIFT_ID


def test_phone_button_uses_premium_icon() -> None:
    kb = phone_request_keyboard()
    btn = kb.keyboard[0][0]

    assert btn.icon_custom_emoji_id == PREMIUM_EMOJI_TOOTH_ID
    assert btn.request_contact is True
