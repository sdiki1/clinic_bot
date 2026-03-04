from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine_and_session(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_pool


def _ensure_users_columns(conn: Connection) -> None:
    inspector = inspect(conn)
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    dialect_name = conn.dialect.name

    statements: list[str] = []
    if "loyalty_opened_at" not in existing_columns:
        if dialect_name == "postgresql":
            statements.append("ALTER TABLE users ADD COLUMN loyalty_opened_at TIMESTAMPTZ NULL")
        else:
            statements.append("ALTER TABLE users ADD COLUMN loyalty_opened_at DATETIME NULL")

    if "loyalty_reminder_sent_count" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN loyalty_reminder_sent_count INTEGER NOT NULL DEFAULT 0")

    if "loyalty_reminder_next_at" not in existing_columns:
        if dialect_name == "postgresql":
            statements.append("ALTER TABLE users ADD COLUMN loyalty_reminder_next_at TIMESTAMPTZ NULL")
        else:
            statements.append("ALTER TABLE users ADD COLUMN loyalty_reminder_next_at DATETIME NULL")

    if "loyalty_reminder_last_sent_at" not in existing_columns:
        if dialect_name == "postgresql":
            statements.append("ALTER TABLE users ADD COLUMN loyalty_reminder_last_sent_at TIMESTAMPTZ NULL")
        else:
            statements.append("ALTER TABLE users ADD COLUMN loyalty_reminder_last_sent_at DATETIME NULL")

    for statement in statements:
        conn.execute(text(statement))


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_users_columns)
