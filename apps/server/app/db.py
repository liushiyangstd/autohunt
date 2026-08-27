"""数据库会话：按数据目录缓存引擎（测试可切 tmp 目录）。"""

from __future__ import annotations

from pathlib import Path

from autohunt_domain.engine import make_engine
from sqlmodel import Session

_engines: dict[str, object] = {}

# PROX-19 技设 §3.1：job 表新增列。`create_all` 不会为既有表补列，
# 本地单机无 Alembic，采用启动时 PRAGMA 检查 + 幂等 ALTER 的轻量迁移（implement Step 0）。
_JOB_NEW_COLUMNS: dict[str, str] = {
    "description": "TEXT",
    "requirements": "JSON",
    "confidence": "VARCHAR",
}


def _migrate_job_columns(engine) -> None:
    """job 表补列（幂等）：已有列跳过，缺失列 ALTER TABLE ADD COLUMN。"""

    with engine.begin() as conn:
        exists = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='job'"
        ).first()
        if exists is None:
            return
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(job)")}
        for name, ddl in _JOB_NEW_COLUMNS.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE job ADD COLUMN {name} {ddl}")


def get_engine(data_dir: Path):
    key = str(data_dir.resolve())
    if key not in _engines:
        engine = make_engine(data_dir / "autohunt.db")
        _migrate_job_columns(engine)
        _engines[key] = engine
    return _engines[key]


def session_for(data_dir: Path) -> Session:
    return Session(get_engine(data_dir))
