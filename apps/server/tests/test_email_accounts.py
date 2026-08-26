"""邮箱账户绑定 / 解绑 / 重授权 —— G3 D4：解绑保留历史事件（AC-8，account_id SET NULL）。"""

from sqlmodel import select

from autohunt_domain.models import EmailAccount, EmailEvent
from app.config import get_settings
from app.db import session_for


def test_unbind_preserves_history_events(client, ui):
    """D4：解绑后关联事件保留，account_id 置空（历史不丢）。"""
    with session_for(get_settings().data_dir) as session:
        session.add(
            EmailAccount(
                id="acc-1", email="me@example.com", imap_host="imap.example.com", auth_code_enc="enc"
            )
        )
        session.add(EmailEvent(account_id="acc-1", message_id="m-1", type="面试", company="字节跳动"))
        session.add(EmailEvent(account_id="acc-1", message_id="m-2", type="拒信", company="腾讯"))
        session.commit()

    resp = client.delete("/api/v1/email-accounts/acc-1", **ui)
    assert resp.status_code == 204

    with session_for(get_settings().data_dir) as session:
        assert session.exec(select(EmailAccount)).first() is None  # 账户已删
        events = session.exec(select(EmailEvent).order_by(EmailEvent.seq)).all()
    assert len(events) == 2  # 事件全部保留
    assert all(e.account_id is None for e in events)  # 外键置空（SET NULL）
    assert events[0].type == "面试"


def test_unbind_unknown_404(client, ui):
    resp = client.delete("/api/v1/email-accounts/nope", **ui)
    assert resp.status_code == 404


def test_email_accounts_ui_only(client, agent):
    assert client.get("/api/v1/email-accounts", **agent).status_code == 403
    assert (
        client.post(
            "/api/v1/email-accounts",
            json={"email": "job@example.com", "imap_host": "imap.example.com", "auth_code": "x"},
            **agent,
        ).status_code
        == 403
    )
