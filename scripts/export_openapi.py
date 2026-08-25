"""导出 OpenAPI 3.1 冻结契约到 docs/design/api-openapi.json。

用法（仓库根目录）：
    python scripts/export_openapi.py

契约变更必须走 PR 评审（技术设计 §3.6 / §9：OpenAPI diff 进 CI，保护外部 Agent）。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "server"))

from app.main import app  # noqa: E402

OUT = ROOT / "docs" / "design" / "api-openapi.json"
OUT.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"wrote {OUT} (openapi {app.openapi()['openapi']})")
