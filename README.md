# Telegram-бот "Стоматология Гид MARULIDI"

Бот автоматически собирает лиды из Telegram, определяет источник трафика по deep-link, запрашивает телефон, выдает PDF-гайд и отправляет уведомление менеджеру.

## Что реализовано

- `/start` + deep-link сегментация: `instagram`, `youtube`, `site`
- Сохранение пользователей в БД (`users`) и заявок (`leads`)
- Запрос телефона через кнопку `📞 Поделиться номером` и ручной ввод
- Валидация телефона (минимум 10 цифр)
- Хранение телефона в безопасном виде: `phone_hash` + `phone_masked`
- Выдача PDF-гайда в зависимости от источника
- Inline-кнопки: `🌐 Перейти на сайт` и `🎁 Мой бонусный счет`
- Переход в бот лояльности с передачей `start=user_<telegram_id>`
- Мгновенное уведомление менеджера о новом лиде
- Повторный заход без повторного запроса номера
- Стартовое сообщение с согласием на документы и кнопкой `Далее`
- Веб-админка: дашборд, лиды, пользователи, загрузка PDF-гайдов и до 7 стартовых документов
- Настраиваемые отложенные сообщения для пользователей, не нажавших кнопку перехода в loyalty-бот

## Стек

- Python 3.11+
- aiogram 3
- SQLAlchemy 2
- PostgreSQL (основная БД)

## Запуск через Docker Compose

1. Создайте `.env`:

```bash
cp .env.example .env
```

2. Заполните обязательные переменные:

- `BOT_TOKEN`
- `MANAGER_CHAT_ID`
- `CLINIC_SITE_URL`
- `LOYALTY_BOT_USERNAME`
- `PHONE_HASH_SALT`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SECRET_KEY`
- `LOYALTY_REMINDER_POLL_SECONDS` (опционально, по умолчанию `60`)
- `LOYALTY_REMINDER_BATCH_SIZE` (опционально, по умолчанию `50`)
- `START_DOCUMENTS_DIR` (опционально, по умолчанию `./guides/start-documents`)

3. Положите PDF-файлы в папку `guides/`:

- `guides/instagram-guide.pdf`
- `guides/youtube-guide.pdf`
- `guides/universal-guide.pdf`
- `guides/terms.pdf` (пользовательское соглашение)
- `guides/privacy-policy.pdf` (политика конфиденциальности)
- `guides/start-documents/*.pdf` (дополнительно: документы, которые отправляются на `/start`, до 7 файлов)

4. Запустите сервисы:

```bash
docker compose up -d --build
```

5. Проверьте логи бота:

```bash
docker compose logs -f bot
```

Логи админ-панели:

```bash
docker compose logs -f admin
```

PostgreSQL поднимается на порту `5123`.

Админ-панель доступна по адресу:
`http://localhost:8080` (или порт из `ADMIN_PANEL_PORT`).

Раздел с настройками напоминаний:
`http://localhost:8080/loyalty-reminders`.

## Параметры PostgreSQL

- `POSTGRES_DB=marulidi_bot`
- `POSTGRES_USER=marulidi`
- `POSTGRES_PASSWORD=marulidi_password`
- `POSTGRES_PORT=5123`
- `DATABASE_URL=postgresql+asyncpg://marulidi:marulidi_password@db:5123/marulidi_bot`
- `ADMIN_PANEL_PORT=8080`

Если запускаете бота не в контейнере, замените хост `db` на `localhost`.

## Локальный запуск без Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e '.[dev]'
python -m bot
```

Для локального запуска с PostgreSQL используйте `DATABASE_URL` вида:
`postgresql+asyncpg://<user>:<password>@localhost:5123/<db_name>`.

Локальный запуск админ-панели:

```bash
uvicorn bot.admin_app:app --host 0.0.0.0 --port 8080 --reload
```

## Ссылки для таргетолога

- Instagram: `https://t.me/<ИмяБота>?start=instagram`
- YouTube: `https://t.me/<ИмяБота>?start=youtube`
- Универсальная: `https://t.me/<ИмяБота>?start=site`
