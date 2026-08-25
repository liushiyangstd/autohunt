"""SQLite 引擎（WAL 模式，技术设计 §4）。

MVP 阶段用 `SQLModel.metadata.create_all` 初始化；Alembic 迁移待数据形态稳定后引入。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine

from autohunt_domain import models as _models  # noqa: F401  确保表已注册到 metadata


def make_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return engine
