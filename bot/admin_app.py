from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from bot.bot_texts import (
    BOT_TEXT_DEFAULTS,
    BOT_TEXT_DEFINITIONS,
    BOT_TEXT_DEFINITIONS_BY_KEY,
    ensure_default_bot_texts,
    get_bot_text_values,
)
from bot.config import Settings, get_settings
from bot.constants import SOURCE_LABELS, SOURCE_UNKNOWN
from bot.database import create_engine_and_session, init_db
from bot.loyalty_reminders import get_or_create_reminder_config
from bot.models import BotText, GuideLink, Lead, LoyaltyReminderConfig, User
from bot.services import (
    build_start_deep_link,
    default_intro_message,
    default_guide_message,
    ensure_default_guide_links,
    guide_pdf_storage_path,
    normalize_public_url,
    normalize_source_key,
)

MAX_GUIDE_SIZE_BYTES = 20 * 1024 * 1024
MAX_START_DOCUMENTS = 7


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return

    db_path = database_url.split("///")[-1]
    if not db_path or db_path == ":memory:":
        return

    path = Path(db_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)


def _is_pdf(filename: str, content: bytes) -> bool:
    return filename.lower().endswith(".pdf") and content.startswith(b"%PDF")


def _sanitize_document_filename(filename: str) -> str:
    base = Path(filename or "").name.strip()
    stem = Path(base).stem.strip() if base else ""
    if not stem:
        stem = "document"
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    safe_stem = safe_stem.strip("_") or "document"
    return f"{safe_stem}.pdf"


def _list_start_documents(settings: Settings) -> list[Path]:
    docs_dir = settings.start_documents_dir
    if not docs_dir.exists() or not docs_dir.is_dir():
        return []

    return sorted(
        [
            path
            for path in docs_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        ],
        key=lambda path: path.name.lower(),
    )


def _resolve_link_pdf_path(settings: Settings, guide_link: GuideLink) -> Path:
    raw_path = (guide_link.pdf_path or "").strip()
    if raw_path:
        return Path(raw_path)
    return guide_pdf_storage_path(settings, guide_link.source)


def _build_uploaded_guide_path(
    settings: Settings,
    filename: str,
    current_path: Path | None = None,
) -> Path:
    base_name = _sanitize_document_filename(filename)
    candidate = settings.guide_links_dir / base_name
    current_path_resolved = current_path.resolve() if current_path else None
    if not candidate.exists() or (current_path_resolved and candidate.resolve() == current_path_resolved):
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = settings.guide_links_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists() or (current_path_resolved and candidate.resolve() == current_path_resolved):
            return candidate
        counter += 1


def _delete_managed_guide_file(settings: Settings, path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    with suppress(ValueError):
        path.resolve().relative_to(settings.guide_links_dir.resolve())
        with suppress(OSError):
            path.unlink()


def _guide_link_view(settings: Settings, guide_link: GuideLink) -> dict[str, str | int | bool]:
    path = _resolve_link_pdf_path(settings, guide_link)
    exists = path.exists()
    name = guide_link.name.strip()
    return {
        "source": guide_link.source,
        "name": name,
        "intro_message_text": (guide_link.intro_message_text or "").strip() or default_intro_message(name),
        "message_text": guide_link.message_text,
        "button_text": guide_link.button_text,
        "button_url": guide_link.button_url,
        "deep_link": build_start_deep_link(settings, guide_link.source),
        "exists": exists,
        "size": path.stat().st_size if exists else 0,
        "path_text": str(path),
    }


def _bot_text_items(values: dict[str, str]) -> list[dict[str, str | bool | int | None]]:
    items: list[dict[str, str | bool | int | None]] = []
    for definition in BOT_TEXT_DEFINITIONS:
        item_value = (values.get(definition.key) or "").strip() or definition.default_value
        items.append(
            {
                "key": definition.key,
                "title": definition.title,
                "description": definition.description,
                "value": item_value,
                "multiline": definition.multiline,
                "rows": definition.rows,
                "max_length": definition.max_length,
            }
        )
    return items


async def _source_labels_map(session: AsyncSession) -> dict[str, str]:
    source_labels = dict(SOURCE_LABELS)
    rows = (await session.execute(select(GuideLink.source, GuideLink.name))).all()
    for source, name in rows:
        source_labels[source] = name

    lead_sources = (await session.execute(select(Lead.source).distinct())).all()
    user_sources = (await session.execute(select(User.source).distinct())).all()
    for (source,) in [*lead_sources, *user_sources]:
        if source and source not in source_labels:
            source_labels[source] = source
    return source_labels


def _ensure_auth(request: Request) -> RedirectResponse | None:
    if request.session.get("admin_ok"):
        return None
    return RedirectResponse(url="/login", status_code=303)


def _check_credentials(settings: Settings, username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password,
        settings.admin_password,
    )


async def _save_guide_file(upload: UploadFile, target_path: Path) -> None:
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(content) > MAX_GUIDE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 20MB)")
    if not _is_pdf(upload.filename or "", content):
        raise HTTPException(status_code=400, detail="Нужно загрузить корректный PDF-файл")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_bytes(content)
    tmp_path.replace(target_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _ensure_sqlite_parent(settings.database_url)

    engine, session_pool = create_engine_and_session(settings.database_url)
    await init_db(engine)
    async with session_pool() as session:
        if await ensure_default_guide_links(session, settings):
            await session.commit()
        if await ensure_default_bot_texts(session):
            await session.commit()

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_pool = session_pool

    try:
        yield
    finally:
        engine: AsyncEngine = app.state.engine
        await engine.dispose()


app = FastAPI(title="MARULIDI Admin", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("ADMIN_SECRET_KEY", "change_me_to_long_random_secret"),
    same_site="lax",
    max_age=12 * 60 * 60,
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


async def get_session(request: Request):
    session_pool: async_sessionmaker[AsyncSession] = request.app.state.session_pool
    async with session_pool() as session:
        yield session


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    users_total = await session.scalar(select(func.count()).select_from(User))
    leads_total = await session.scalar(select(func.count()).select_from(Lead))

    latest_leads = (
        await session.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(10))
    ).all()

    leads_by_source_rows = (
        await session.execute(
            select(Lead.source, func.count(Lead.id)).group_by(Lead.source).order_by(func.count(Lead.id).desc())
        )
    ).all()
    source_labels = await _source_labels_map(session)

    leads_by_source = [
        {
            "source": source_labels.get(source, source or "Не определен"),
            "count": count,
        }
        for source, count in leads_by_source_rows
    ]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Дашборд",
            "users_total": users_total or 0,
            "leads_total": leads_total or 0,
            "latest_leads": latest_leads,
            "leads_by_source": leads_by_source,
            "source_labels": source_labels,
        },
    )


@app.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    source: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    stmt = select(User).order_by(User.reg_date.desc())
    if source:
        stmt = stmt.where(User.source == source)
    users = (await session.scalars(stmt.limit(200))).all()
    source_labels = await _source_labels_map(session)

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "title": "Пользователи",
            "users": users,
            "selected_source": source or "",
            "source_labels": source_labels,
        },
    )


@app.get("/leads", response_class=HTMLResponse)
async def leads_page(
    request: Request,
    source: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    stmt = select(Lead).order_by(Lead.created_at.desc())
    if source:
        stmt = stmt.where(Lead.source == source)
    leads = (await session.scalars(stmt.limit(200))).all()
    source_labels = await _source_labels_map(session)

    return templates.TemplateResponse(
        request=request,
        name="leads.html",
        context={
            "title": "Лиды",
            "leads": leads,
            "selected_source": source or "",
            "source_labels": source_labels,
        },
    )


@app.get("/guides", response_class=HTMLResponse)
async def guides_page(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    guide_links = (
        await session.scalars(select(GuideLink).order_by(GuideLink.created_at.asc(), GuideLink.id.asc()))
    ).all()
    guides = [_guide_link_view(settings, row) for row in guide_links]

    return templates.TemplateResponse(
        request=request,
        name="guides.html",
        context={
            "title": "Гайды",
            "guides": guides,
            "bot_username": settings.bot_username,
            "msg": msg,
            "err": err,
        },
    )


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    documents = [
        {
            "filename": path.name,
            "size": path.stat().st_size,
            "path_text": str(path),
        }
        for path in _list_start_documents(settings)
    ]

    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            "title": "Документы",
            "documents": documents,
            "max_docs": MAX_START_DOCUMENTS,
            "msg": msg,
            "err": err,
        },
    )


@app.get("/loyalty-reminders", response_class=HTMLResponse)
async def loyalty_reminders_page(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    config = await session.get(LoyaltyReminderConfig, 1)
    if config is None:
        config = await get_or_create_reminder_config(session)
        await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="loyalty_reminders.html",
        context={
            "title": "Loyalty Напоминания",
            "config": config,
            "msg": msg,
            "err": err,
        },
    )


@app.get("/bot-texts", response_class=HTMLResponse)
async def bot_texts_page(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    if await ensure_default_bot_texts(session):
        await session.commit()

    values = await get_bot_text_values(session)
    return templates.TemplateResponse(
        request=request,
        name="bot_texts.html",
        context={
            "title": "Тексты Бота",
            "items": _bot_text_items(values),
            "msg": msg,
            "err": err,
        },
    )


@app.post("/bot-texts")
async def save_bot_texts(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    if await ensure_default_bot_texts(session):
        await session.flush()

    existing_rows = (await session.scalars(select(BotText))).all()
    existing_by_key = {row.key: row for row in existing_rows}
    form = await request.form()

    for key, default_value in BOT_TEXT_DEFAULTS.items():
        definition = BOT_TEXT_DEFINITIONS_BY_KEY[key]
        raw_value = str(form.get(key, "")).strip()
        value = raw_value or default_value

        if definition.max_length is not None and len(value) > definition.max_length:
            error_message = f"Поле «{definition.title}» превышает лимит: {definition.max_length} символов"
            return RedirectResponse(
                url=f"/bot-texts?err={quote_plus(error_message)}",
                status_code=303,
            )

        row = existing_by_key.get(key)
        if row is None:
            row = BotText(key=key, value=value)
            session.add(row)
            existing_by_key[key] = row
            continue
        row.value = value

    await session.commit()
    return RedirectResponse(
        url=f"/bot-texts?msg={quote_plus('Тексты сохранены')}",
        status_code=303,
    )


@app.post("/guides/create")
async def create_guide_link(
    request: Request,
    source: str = Form(...),
    name: str = Form(...),
    intro_message_text: str = Form(""),
    message_text: str = Form(...),
    button_text: str = Form(...),
    button_url: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    source_key = normalize_source_key(source)
    if source_key is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Ключ ссылки должен быть в формате a-z, 0-9, _, - (до 64 символов)')}",
            status_code=303,
        )
    if source_key == SOURCE_UNKNOWN:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Ключ unknown зарезервирован')}",
            status_code=303,
        )

    existing = await session.scalar(select(GuideLink).where(GuideLink.source == source_key))
    if existing is not None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Ссылка с таким ключом уже существует')}",
            status_code=303,
        )

    name_value = name.strip()
    if not name_value:
        return RedirectResponse(url=f"/guides?err={quote_plus('Название обязательно')}", status_code=303)
    if len(name_value) > 128:
        return RedirectResponse(url=f"/guides?err={quote_plus('Название слишком длинное (макс. 128)')}", status_code=303)

    intro_message_value = intro_message_text.strip() or default_intro_message(name_value)
    if len(intro_message_value) > 2048:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Первое сообщение должно быть до 2048 символов')}",
            status_code=303,
        )

    message_value = message_text.strip() or default_guide_message(name_value)
    if len(message_value) > 1024:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Сообщение должно быть до 1024 символов')}",
            status_code=303,
        )

    button_text_value = button_text.strip() or "Перейти на сайт"
    if len(button_text_value) > 96:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Текст кнопки слишком длинный (макс. 96)')}",
            status_code=303,
        )

    button_url_value = normalize_public_url(button_url)
    if button_url_value is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('URL кнопки должен начинаться с http:// или https://')}",
            status_code=303,
        )

    session.add(
        GuideLink(
            source=source_key,
            name=name_value,
            intro_message_text=intro_message_value,
            message_text=message_value,
            button_text=button_text_value,
            button_url=button_url_value,
            pdf_path=str(guide_pdf_storage_path(settings, source_key)),
        )
    )
    await session.commit()
    return RedirectResponse(
        url=f"/guides?msg={quote_plus('Ссылка создана')}",
        status_code=303,
    )


@app.post("/guides/update/{source}")
async def update_guide_link(
    request: Request,
    source: str,
    name: str = Form(...),
    intro_message_text: str = Form(...),
    message_text: str = Form(...),
    button_text: str = Form(...),
    button_url: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    source_key = normalize_source_key(source)
    if source_key is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Некорректный ключ ссылки')}",
            status_code=303,
        )

    guide_link = await session.scalar(select(GuideLink).where(GuideLink.source == source_key))
    if guide_link is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Ссылка не найдена')}",
            status_code=303,
        )

    name_value = name.strip()
    if not name_value:
        return RedirectResponse(url=f"/guides?err={quote_plus('Название обязательно')}", status_code=303)
    if len(name_value) > 128:
        return RedirectResponse(url=f"/guides?err={quote_plus('Название слишком длинное (макс. 128)')}", status_code=303)

    intro_message_value = intro_message_text.strip() or default_intro_message(name_value)
    if len(intro_message_value) > 2048:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Первое сообщение должно быть до 2048 символов')}",
            status_code=303,
        )

    message_value = message_text.strip() or default_guide_message(name_value)
    if len(message_value) > 1024:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Сообщение должно быть до 1024 символов')}",
            status_code=303,
        )

    button_text_value = button_text.strip() or "Перейти на сайт"
    if len(button_text_value) > 96:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Текст кнопки слишком длинный (макс. 96)')}",
            status_code=303,
        )

    button_url_value = normalize_public_url(button_url)
    if button_url_value is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('URL кнопки должен начинаться с http:// или https://')}",
            status_code=303,
        )

    guide_link.name = name_value
    guide_link.intro_message_text = intro_message_value
    guide_link.message_text = message_value
    guide_link.button_text = button_text_value
    guide_link.button_url = button_url_value
    await session.commit()
    return RedirectResponse(
        url=f"/guides?msg={quote_plus('Настройки ссылки сохранены')}",
        status_code=303,
    )


@app.post("/guides/upload/{source}")
async def upload_guide(
    request: Request,
    source: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    source_key = normalize_source_key(source)
    if source_key is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Некорректный ключ ссылки')}",
            status_code=303,
        )

    guide_link = await session.scalar(select(GuideLink).where(GuideLink.source == source_key))
    if guide_link is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Ссылка не найдена')}",
            status_code=303,
        )

    previous_path = _resolve_link_pdf_path(settings, guide_link)
    target_path = _build_uploaded_guide_path(
        settings,
        file.filename or f"{source_key}.pdf",
        current_path=previous_path,
    )

    try:
        await _save_guide_file(file, target_path)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/guides?err={quote_plus(str(exc.detail))}",
            status_code=303,
        )

    guide_link.pdf_path = str(target_path)
    await session.commit()
    if previous_path.resolve() != target_path.resolve():
        _delete_managed_guide_file(settings, previous_path)

    return RedirectResponse(
        url=f"/guides?msg={quote_plus('Файл успешно обновлен')}",
        status_code=303,
    )


@app.post("/guides/delete/{source}")
async def delete_guide_link(
    request: Request,
    source: str,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    source_key = normalize_source_key(source)
    if source_key is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Некорректный ключ ссылки')}",
            status_code=303,
        )

    guide_link = await session.scalar(select(GuideLink).where(GuideLink.source == source_key))
    if guide_link is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Ссылка не найдена')}",
            status_code=303,
        )

    pdf_path = _resolve_link_pdf_path(settings, guide_link)
    await session.delete(guide_link)
    await session.commit()

    _delete_managed_guide_file(settings, pdf_path)

    return RedirectResponse(
        url=f"/guides?msg={quote_plus('Ссылка удалена')}",
        status_code=303,
    )


@app.post("/documents/upload")
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    if not files:
        return RedirectResponse(url=f"/documents?err={quote_plus('Файлы не переданы')}", status_code=303)
    if len(files) > MAX_START_DOCUMENTS:
        return RedirectResponse(
            url=f"/documents?err={quote_plus('За раз можно загрузить не более 7 файлов')}",
            status_code=303,
        )

    existing_paths = _list_start_documents(settings)
    existing_names = {path.name for path in existing_paths}
    incoming_targets: list[tuple[UploadFile, str]] = []
    new_names: set[str] = set()

    for upload in files:
        sanitized_name = _sanitize_document_filename(upload.filename or "")
        if sanitized_name in existing_names:
            incoming_targets.append((upload, sanitized_name))
            continue

        stem = Path(sanitized_name).stem
        candidate = sanitized_name
        counter = 1
        while candidate in existing_names or candidate in new_names:
            candidate = f"{stem}-{counter}.pdf"
            counter += 1
        new_names.add(candidate)
        incoming_targets.append((upload, candidate))

    if len(existing_names) + len(new_names) > MAX_START_DOCUMENTS:
        return RedirectResponse(
            url=f"/documents?err={quote_plus('В разделе документов максимум 7 файлов')}",
            status_code=303,
        )

    for upload, filename in incoming_targets:
        target_path = settings.start_documents_dir / filename
        try:
            await _save_guide_file(upload, target_path)
        except HTTPException as exc:
            return RedirectResponse(
                url=f"/documents?err={quote_plus(str(exc.detail))}",
                status_code=303,
            )

    return RedirectResponse(
        url=f"/documents?msg={quote_plus('Файлы успешно загружены')}",
        status_code=303,
    )


@app.post("/documents/delete/{filename:path}")
async def delete_document(
    request: Request,
    filename: str,
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings
    safe_name = _sanitize_document_filename(filename)
    target_path = settings.start_documents_dir / safe_name
    if target_path.exists():
        target_path.unlink()

    return RedirectResponse(
        url=f"/documents?msg={quote_plus('Файл удален')}",
        status_code=303,
    )


@app.post("/loyalty-reminders")
async def save_loyalty_reminders(
    request: Request,
    enabled: str | None = Form(default=None),
    message_24h: str = Form(...),
    message_5d: str = Form(...),
    message_7d: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    msg_24h = message_24h.strip()
    msg_5d = message_5d.strip()
    msg_7d = message_7d.strip()
    if not msg_24h or not msg_5d or not msg_7d:
        return RedirectResponse(
            url=f"/loyalty-reminders?err={quote_plus('Все три текста обязательны')}",
            status_code=303,
        )

    config = await get_or_create_reminder_config(session)
    config.enabled = enabled is not None
    config.message_24h = msg_24h
    config.message_5d = msg_5d
    config.message_7d = msg_7d
    await session.commit()

    return RedirectResponse(
        url=f"/loyalty-reminders?msg={quote_plus('Настройки сохранены')}",
        status_code=303,
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, err: str | None = None) -> HTMLResponse:
    if request.session.get("admin_ok"):
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"title": "Вход", "err": err},
    )


@app.post("/login")
async def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    settings: Settings = request.app.state.settings

    if not _check_credentials(settings, username.strip(), password):
        return RedirectResponse(url="/login?err=Неверный+логин+или+пароль", status_code=303)

    request.session["admin_ok"] = True
    request.session["admin_username"] = settings.admin_username
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
async def logout_action(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
