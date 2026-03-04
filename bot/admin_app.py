from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from bot.config import Settings, get_settings
from bot.constants import SOURCE_LABELS
from bot.database import create_engine_and_session, init_db
from bot.loyalty_reminders import get_or_create_reminder_config
from bot.models import Lead, LoyaltyReminderConfig, User

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


def _guide_definitions(settings: Settings) -> list[dict[str, Any]]:
    return [
        {
            "key": "instagram",
            "title": "Instagram Гайд",
            "path": settings.guide_instagram_path,
        },
        {
            "key": "youtube",
            "title": "YouTube Гайд",
            "path": settings.guide_youtube_path,
        },
        {
            "key": "default",
            "title": "Универсальный Гайд",
            "path": settings.guide_default_path,
        },
    ]


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

    leads_by_source = [
        {
            "source": SOURCE_LABELS.get(source, source or "Не определен"),
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
            "source_labels": SOURCE_LABELS,
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

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "title": "Пользователи",
            "users": users,
            "selected_source": source or "",
            "source_labels": SOURCE_LABELS,
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

    return templates.TemplateResponse(
        request=request,
        name="leads.html",
        context={
            "title": "Лиды",
            "leads": leads,
            "selected_source": source or "",
            "source_labels": SOURCE_LABELS,
        },
    )


@app.get("/guides", response_class=HTMLResponse)
async def guides_page(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings

    guides = []
    for item in _guide_definitions(settings):
        path: Path | None = item["path"]
        exists = bool(path and path.exists())
        size = path.stat().st_size if exists else 0
        guides.append(
            {
                **item,
                "exists": exists,
                "size": size,
                "path_text": str(path) if path else "не настроен",
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="guides.html",
        context={
            "title": "Гайды",
            "guides": guides,
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


@app.post("/guides/upload/{guide_key}")
async def upload_guide(
    request: Request,
    guide_key: str,
    file: UploadFile = File(...),
) -> RedirectResponse:
    unauthorized = _ensure_auth(request)
    if unauthorized:
        return unauthorized

    settings: Settings = request.app.state.settings

    target_map = {
        "instagram": settings.guide_instagram_path,
        "youtube": settings.guide_youtube_path,
        "default": settings.guide_default_path,
    }

    target_path = target_map.get(guide_key)
    if target_path is None:
        return RedirectResponse(
            url=f"/guides?err={quote_plus('Неизвестный тип гайда')}",
            status_code=303,
        )

    try:
        await _save_guide_file(file, target_path)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/guides?err={quote_plus(str(exc.detail))}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/guides?msg={quote_plus('Файл успешно обновлен')}",
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
