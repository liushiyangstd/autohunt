"""IMAP 连接原语（FR-40/44）：可注入的连接工厂，测试打桩免真实网络。

`verify_credentials` 供绑定前预检 / 重授权；`connect` 供 Worker 轮询。
认证失败抛 `AuthFailed`（区别于网络等瞬时错误），调用方据此置 auth_failed。
"""

from __future__ import annotations

import imaplib


class AuthFailed(Exception):
    """IMAP 认证失败（授权码错误/过期）——FR-44 授权失效信号。"""


def connect(host: str, port: int, email: str, auth_code: str, timeout: int = 30):
    """建立 IMAP4_SSL 连接并登录；认证失败抛 AuthFailed，网络错误原样上抛。"""

    client = imaplib.IMAP4_SSL(host, port, timeout=timeout)
    try:
        client.login(email, auth_code)
    except imaplib.IMAP4.error as exc:
        try:
            client.logout()
        except Exception:  # noqa: BLE001
            pass
        raise AuthFailed(str(exc) or "IMAP 认证失败") from exc
    return client


def verify_credentials(email: str, host: str, port: int, auth_code: str, timeout: int = 15) -> str | None:
    """连接预检：成功返回 None，失败返回原因字符串（不落库，供 test/bind 端点）。"""

    try:
        client = connect(host, port, email, auth_code, timeout=timeout)
    except AuthFailed as exc:
        return f"认证失败：{exc}"
    except Exception as exc:  # noqa: BLE001 — 网络/SSL/DNS 等统一归为连接失败原因
        return f"连接失败：{exc}"
    try:
        client.logout()
    except Exception:  # noqa: BLE001
        pass
    return None
