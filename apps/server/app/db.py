"""数据库会话：按数据目录缓存引擎（测试可切 tmp 目录）。"""

from __future__ import annotations

from pathlib import Path

from autohunt_domain.engine import make_engine
from sqlmodel import Session

_engines: dict[str, object] = {}


def get_engine(data_dir: Path):
    key = str(data_dir.resolve())
    if key not in _engines:
        _engines[key] = make_engine(data_dir / "autohunt.db")
    return _engines[key]


def session_for(data_dir: Path) -> Session:
    return Session(get_engine(data_dir))
