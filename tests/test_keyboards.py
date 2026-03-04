from bot.constants import PREMIUM_EMOJI_GIFT_ID, PREMIUM_EMOJI_TOOTH_ID, PREMIUM_EMOJI_WORLD_ID
from bot.keyboards import actions_inline_keyboard, loyalty_url_keyboard, phone_request_keyboard, start_consent_keyboard


def test_actions_inline_keyboard_styles_and_icons() -> None:
    kb = actions_inline_keyboard("https://example.com", "https://t.me/bonus_bot")

    site_btn = kb.inline_keyboard[0][0]
    loyalty_btn = kb.inline_keyboard[1][0]

    assert site_btn.style == "primary"
    assert site_btn.icon_custom_emoji_id == PREMIUM_EMOJI_WORLD_ID

    assert loyalty_btn.style == "success"
    assert loyalty_btn.icon_custom_emoji_id == PREMIUM_EMOJI_GIFT_ID
    assert loyalty_btn.callback_data == "open_loyalty"


def test_phone_button_uses_premium_icon() -> None:
    kb = phone_request_keyboard()
    btn = kb.keyboard[0][0]

    assert btn.icon_custom_emoji_id == PREMIUM_EMOJI_TOOTH_ID
    assert btn.request_contact is True


def test_start_consent_keyboard() -> None:
    kb = start_consent_keyboard("instagram")
    btn = kb.inline_keyboard[0][0]

    assert btn.text == "Далее"
    assert btn.style == "primary"
    assert btn.icon_custom_emoji_id == PREMIUM_EMOJI_TOOTH_ID
    assert btn.callback_data == "start_continue:instagram"


def test_loyalty_url_keyboard() -> None:
    kb = loyalty_url_keyboard("https://t.me/bonus_bot?start=user_1")
    btn = kb.inline_keyboard[0][0]

    assert btn.style == "success"
    assert btn.icon_custom_emoji_id == PREMIUM_EMOJI_GIFT_ID
    assert btn.url == "https://t.me/bonus_bot?start=user_1"
