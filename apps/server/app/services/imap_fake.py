"""IMAP test double（Tester §17 钩子 ①）——`AUTOHUNT_IMAP_BACKEND=fake` 时启用。

由 `POST /__test__/imap/configure` 脚本化三种行为（认证通过/认证失败/连接失败）
与预置邮件；`fake_connect` 返回的 `FakeIMAPClient` 实现 Worker 依赖的
`select/uid/logout` 三个原语，按 store 中的邮件列表模拟 UID 增量拉取。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.imap_client import AuthFailed


@dataclass
class FakeImapStore:
    mode: str = "ok"  # ok / auth_fail / conn_fail
    messages: list[bytes] = field(default_factory=list)  # 每条一封原始 EML

    def reset(self) -> None:
        self.mode = "ok"
        self.messages = []


_store = FakeImapStore()


def get_store() -> FakeImapStore:
    return _store


def fake_connect(host: str, port: int, email: str, auth_code: str, timeout: int = 30):
    if _store.mode == "auth_fail":
        raise AuthFailed("fake: 认证失败（授权码错误/过期）")
    if _store.mode == "conn_fail":
        raise ConnectionError("fake: 连接失败（网络/DNS/超时）")
    return FakeIMAPClient(_store)


class FakeIMAPClient:
    """Worker 用 IMAP 客户端最小接口的假实现；UID 从 1 起对应 store.messages。"""

    def __init__(self, store: FakeImapStore):
        self._store = store

    def select(self, mailbox: str):
        return ("OK", [b"1"])

    def uid(self, command: str, *args):
        if command == "SEARCH":
            uids = [str(i + 1) for i in range(len(self._store.messages))]
            return ("OK", [b" ".join(u.encode() for u in uids)])
        if command == "FETCH":
            uid = int(args[0])
            if 1 <= uid <= len(self._store.messages):
                return ("OK", [(f"{uid} (RFC822)".encode(), self._store.messages[uid - 1])])
            return ("OK", [])
        return ("OK", [b""])

    def logout(self):
        return ("BYE", [b""])
