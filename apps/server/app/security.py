"""凭证与令牌原语（§2.2 密钥存储 / §3.4 submit_token）。

- API key：只存 SHA-256 哈希 + 前缀，完整 key 仅创建时返回一次。
- submit_token：需经 GET /confirmations/{id} 返回给 Agent，无法只存哈希 ——
  用 Fernet 对称加密落盘（与邮箱授权码同口径），另存 confirmed_fields 绑定哈希。
- Fernet 密钥置于数据目录 secret_key 文件（用户本机，0600 尽力设置）。
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

_fernet_cache: dict[str, Fernet] = {}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"ah_live_{secrets.token_urlsafe(24)}"


def generate_submit_token() -> str:
    return f"ah_submit_{secrets.token_urlsafe(24)}"


def fields_hash(confirmed_fields: dict[str, str]) -> str:
    """confirmed_fields 绑定哈希：规范化 JSON 后取 SHA-256（篡改即失配）。"""

    canonical = json.dumps(confirmed_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical)


def get_fernet(data_dir: Path) -> Fernet:
    key_path = data_dir / "secret_key"
    cache_key = str(key_path.resolve())
    if cache_key in _fernet_cache:
        return _fernet_cache[cache_key]
    data_dir.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except OSError:
            pass  # Windows 上尽力即可
    fernet = Fernet(key)
    _fernet_cache[cache_key] = fernet
    return fernet


def encrypt(data_dir: Path, plaintext: str) -> str:
    return get_fernet(data_dir).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(data_dir: Path, ciphertext: str) -> str:
    return get_fernet(data_dir).decrypt(ciphertext.encode("ascii")).decode("utf-8")
