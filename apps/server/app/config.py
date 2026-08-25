"""运行配置（环境变量驱动）。

- AUTOHUNT_DATA_DIR：数据目录（默认 ./data），存 SQLite / 会话令牌 / Fernet 密钥
- AUTOHUNT_UI_TOKEN：测试/运维注入的 UI session token；缺省时首启生成并落盘
- AUTOHUNT_SUBMIT_TOKEN_TTL_SECONDS：submit_token TTL（默认 1800；测试钩子①，可调小加速过期）
- AUTOHUNT_TEST_HOOKS=1：挂载隐藏测试钩子路由（不进 OpenAPI；测试钩子②等）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    ui_token: str | None
    submit_token_ttl_seconds: int
    test_hooks: bool


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("AUTOHUNT_DATA_DIR", "data")),
        ui_token=os.environ.get("AUTOHUNT_UI_TOKEN") or None,
        submit_token_ttl_seconds=int(os.environ.get("AUTOHUNT_SUBMIT_TOKEN_TTL_SECONDS", "1800")),
        test_hooks=os.environ.get("AUTOHUNT_TEST_HOOKS") == "1",
    )
