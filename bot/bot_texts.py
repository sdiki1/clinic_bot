from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import BotText


@dataclass(frozen=True)
class BotTextDefinition:
    key: str
    title: str
    description: str
    default_value: str
    multiline: bool = True
    rows: int = 3
    max_length: int | None = None


BOT_TEXT_DEFINITIONS: tuple[BotTextDefinition, ...] = (
    BotTextDefinition(
        key="links_menu_message",
        title="Меню для зарегистрированного пользователя",
        description="Показывается, когда пользователь уже зарегистрирован. Плейсхолдеры: {emoji_tooth}, {emoji_world}, {emoji_gift}.",
        default_value=(
            "{emoji_tooth} С возвращением!\n"
            "{emoji_world} Можете перейти на сайт клиники или в систему лояльности.\n"
            "{emoji_gift} Нажмите «Система лояльности», чтобы получить ссылку на переход.\n"
            "Если хотите снова получить материал, используйте команду /guide."
        ),
        rows=5,
        max_length=4096,
    ),
    BotTextDefinition(
        key="guide_unavailable_message",
        title="Сообщение при отсутствии файла гайда",
        description="Показывается, если PDF временно недоступен. Плейсхолдер: {emoji_books}.",
        default_value=(
            "{emoji_books} Спасибо за заявку!\n"
            "Сейчас файл временно недоступен, но вы уже можете перейти на сайт или в систему лояльности."
        ),
        rows=4,
        max_length=4096,
    ),
    BotTextDefinition(
        key="phone_parse_error_message",
        title="Ошибка распознавания номера",
        description="Отправляется, если номер не удалось распознать.",
        default_value=(
            "⚠️ Не получилось распознать номер.\n"
            "Пожалуйста, отправьте номер в формате +79991234567 или минимум 10 цифр."
        ),
        rows=4,
        max_length=4096,
    ),
    BotTextDefinition(
        key="phone_already_saved_message",
        title="Номер уже сохранен",
        description="Показывается, если пользователь отправляет номер повторно.",
        default_value="✅ Номер уже сохранен.",
        rows=2,
        max_length=4096,
    ),
    BotTextDefinition(
        key="phone_saved_message",
        title="Номер успешно сохранен",
        description="Показывается после успешного сохранения номера.",
        default_value="✅ Спасибо! Номер сохранен.",
        rows=2,
        max_length=4096,
    ),
    BotTextDefinition(
        key="already_registered_message",
        title="Пользователь уже зарегистрирован",
        description="Показывается при повторном старте для зарегистрированного пользователя. Плейсхолдер: {emoji_greeting}.",
        default_value="{emoji_greeting} Вы уже зарегистрированы.",
        rows=2,
        max_length=4096,
    ),
    BotTextDefinition(
        key="consent_message",
        title="Текст согласия перед кнопкой «Далее»",
        description="Показывается новым пользователям перед продолжением сценария.",
        default_value=(
            "Нажимая кнопку «Далее», Вы соглашаетесь с:\n"
            "• Политикой обработки персональных данных\n"
            "• Получением информационно-рекламных сообщений"
        ),
        rows=4,
        max_length=4096,
    ),
    BotTextDefinition(
        key="loyalty_link_toast",
        title="Подсказка после нажатия «Система лояльности»",
        description="Короткий текст во всплывающем уведомлении callback-query (до 200 символов).",
        default_value="Отправил ссылку на систему лояльности",
        multiline=False,
        rows=1,
        max_length=200,
    ),
    BotTextDefinition(
        key="loyalty_link_message",
        title="Сообщение со ссылкой на loyalty-бот",
        description="Показывается отдельным сообщением после нажатия кнопки. Плейсхолдеры: {emoji_gift}, {loyalty_url}.",
        default_value="{emoji_gift} Перейти в систему лояльности:\n{loyalty_url}",
        rows=3,
        max_length=4096,
    ),
    BotTextDefinition(
        key="guide_requires_phone_message",
        title="Команда /guide без номера",
        description="Показывается, если пользователь запросил гайд без сохраненного телефона.",
        default_value="📞 Сначала поделитесь номером телефона, чтобы получить гайд.",
        rows=3,
        max_length=4096,
    ),
    BotTextDefinition(
        key="send_own_phone_message",
        title="Отправлен чужой контакт",
        description="Показывается, если пользователь отправил не свой контакт.",
        default_value="⚠️ Отправьте, пожалуйста, свой номер через кнопку ниже.",
        rows=3,
        max_length=4096,
    ),
    BotTextDefinition(
        key="manager_notification_template",
        title="Шаблон уведомления менеджеру",
        description=(
            "Плейсхолдеры: {first_name}, {username_line}, {telegram_id}, {phone}, {source}, {lead_time}."
        ),
        default_value=(
            "🚨 Новый лид\n"
            "Имя: {first_name}\n"
            "Username: {username_line}\n"
            "Telegram ID: {telegram_id}\n"
            "Телефон: {phone}\n"
            "Источник: {source}\n"
            "Дата: {lead_time}"
        ),
        rows=7,
        max_length=4096,
    ),
    BotTextDefinition(
        key="new_user_notification_template",
        title="Шаблон уведомления о новом пользователе",
        description=(
            "Плейсхолдеры: {registered_at}, {first_name}, {username_line}, {telegram_id}, {phone}, {source}."
        ),
        default_value=(
            "Новый пользователь:\n"
            "Дата: {registered_at}\n"
            "Имя: {first_name}\n"
            "User: {username_line}\n"
            "Id: {telegram_id}\n"
            "Телефон: {phone}\n"
            "Источник: {source}"
        ),
        rows=7,
        max_length=4096,
    ),
    BotTextDefinition(
        key="phone_request_button_text",
        title="Текст кнопки «Поделиться номером»",
        description="Кнопка запроса контакта у пользователя.",
        default_value="Поделиться номером",
        multiline=False,
        rows=1,
        max_length=64,
    ),
    BotTextDefinition(
        key="phone_request_input_placeholder",
        title="Подсказка в поле ввода номера",
        description="Placeholder под клавиатурой запроса контакта.",
        default_value="Нажмите кнопку или введите номер вручную",
        multiline=False,
        rows=1,
        max_length=64,
    ),
    BotTextDefinition(
        key="start_continue_button_text",
        title="Текст кнопки «Далее»",
        description="Кнопка продолжения стартового сценария.",
        default_value="Далее",
        multiline=False,
        rows=1,
        max_length=64,
    ),
    BotTextDefinition(
        key="loyalty_open_button_text",
        title="Текст кнопки перехода в loyalty-бот",
        description="Текст URL-кнопки в сообщении с loyalty-ссылкой.",
        default_value="Перейти в систему лояльности",
        multiline=False,
        rows=1,
        max_length=64,
    ),
    BotTextDefinition(
        key="actions_loyalty_button_text",
        title="Текст кнопки «Система лояльности»",
        description="Текст inline-кнопки в основном меню действий.",
        default_value="Система лояльности",
        multiline=False,
        rows=1,
        max_length=64,
    ),
)

BOT_TEXT_DEFAULTS: dict[str, str] = {
    definition.key: definition.default_value for definition in BOT_TEXT_DEFINITIONS
}

BOT_TEXT_DEFINITIONS_BY_KEY: dict[str, BotTextDefinition] = {
    definition.key: definition for definition in BOT_TEXT_DEFINITIONS
}

START_BOT_TEXT_KEYS: tuple[str, ...] = (
    "consent_message",
    "already_registered_message",
    "links_menu_message",
    "start_continue_button_text",
    "phone_request_button_text",
    "phone_request_input_placeholder",
    "actions_loyalty_button_text",
)


class _SafeTemplateValues(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_bot_text(template: str, **values: object) -> str:
    if not template:
        return ""
    try:
        return template.format_map(_SafeTemplateValues(values))
    except Exception:
        return template


async def ensure_default_bot_texts(session: AsyncSession) -> bool:
    existing_rows = (await session.scalars(select(BotText))).all()
    existing_by_key = {row.key: row for row in existing_rows}

    changed = False
    for definition in BOT_TEXT_DEFINITIONS:
        if definition.key in existing_by_key:
            continue
        session.add(BotText(key=definition.key, value=definition.default_value))
        changed = True

    if changed:
        await session.flush()
    return changed


async def get_bot_text_values(session: AsyncSession) -> dict[str, str]:
    rows = (await session.scalars(select(BotText))).all()
    values = dict(BOT_TEXT_DEFAULTS)

    for row in rows:
        value = (row.value or "").strip()
        if not value:
            continue
        values[row.key] = value

    return values
