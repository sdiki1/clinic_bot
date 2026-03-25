from bot.bot_texts import BOT_TEXT_DEFAULTS, BOT_TEXT_DEFINITIONS, render_bot_text


def test_bot_text_keys_are_unique() -> None:
    keys = [item.key for item in BOT_TEXT_DEFINITIONS]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(BOT_TEXT_DEFAULTS)


def test_render_bot_text_substitutes_known_placeholders() -> None:
    text = render_bot_text("Привет, {name}!", name="Анна")
    assert text == "Привет, Анна!"


def test_render_bot_text_keeps_unknown_placeholders() -> None:
    text = render_bot_text("Ссылка: {loyalty_url}")
    assert text == "Ссылка: {loyalty_url}"


def test_render_bot_text_returns_original_on_invalid_template() -> None:
    text = render_bot_text("Текст с {некорректным")
    assert text == "Текст с {некорректным"
