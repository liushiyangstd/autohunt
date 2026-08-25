"""状态机（BR-10/BR-11，§5）—— 唯一裁决点，所有状态写路径必经。

主链 rank 递增：待投递(0) → 已投递(1) → 笔试(2) → 面试(3) → offer(4) → 已接受/已拒绝(5)
旁路终止态：未通过 / 主动放弃 / 已过期（无 rank；进入后仅 UI 可重开为待投递）。

裁决规则：
- ui：允许任意合法流转（含回退与终态重开，用户即确认者）。
- agent / email（自动来源）：非终态主链仅许 rank 前进；同态重复写入幂等成功（不写历史）；
  回退一律 409 并落 rejected history。终态进入按来源白名单：email → 未通过/已拒绝，
  agent → 未通过；主动放弃/已过期/已接受仅 UI；终态之后自动来源一律拒绝。
"""

from __future__ import annotations

from sqlmodel import Session

from autohunt_domain.models import Application, StatusHistory
from app.errors import state_conflict
from app.schemas import ApplicationStatus

MAIN_RANK: dict[ApplicationStatus, int] = {
    ApplicationStatus.pending: 0,
    ApplicationStatus.submitted: 1,
    ApplicationStatus.written_test: 2,
    ApplicationStatus.interview: 3,
    ApplicationStatus.offer: 4,
    ApplicationStatus.accepted: 5,
    ApplicationStatus.rejected: 5,
}

TERMINAL: set[ApplicationStatus] = {
    ApplicationStatus.accepted,
    ApplicationStatus.rejected,
    ApplicationStatus.failed,
    ApplicationStatus.abandoned,
    ApplicationStatus.expired,
}

# 自动来源进入终态的白名单（§5 旁路终止态规则；已接受只能由用户标记）
AUTO_TERMINAL_WHITELIST: dict[str, set[ApplicationStatus]] = {
    "email": {ApplicationStatus.failed, ApplicationStatus.rejected},
    "agent": {ApplicationStatus.failed},
}


class Decision:
    def __init__(self, allowed: bool, idempotent: bool = False, reason: str = ""):
        self.allowed = allowed
        self.idempotent = idempotent  # 同态重复写入：成功返回但不写历史
        self.reason = reason


def can_transition(current: ApplicationStatus, target: ApplicationStatus, source: str) -> Decision:
    if source == "ui":
        return Decision(True, idempotent=(current == target))

    if current in TERMINAL:
        return Decision(False, reason=f"终态「{current.value}」之后仅 UI 可重开")

    if target in TERMINAL:
        whitelist = AUTO_TERMINAL_WHITELIST.get(source, set())
        if target in whitelist:
            return Decision(True)
        return Decision(
            False,
            reason=f"自动来源（{source}）不得进入终态「{target.value}」（白名单外，BR-11/§5）",
        )

    cur_rank, tgt_rank = MAIN_RANK[current], MAIN_RANK[target]
    if tgt_rank > cur_rank:
        return Decision(True)
    if tgt_rank == cur_rank:
        return Decision(True, idempotent=True)
    return Decision(
        False,
        reason=f"自动来源（{source}）不得回退状态：{current.value} → {target.value}（BR-11）",
    )


def apply_transition(
    session: Session,
    application: Application,
    target: ApplicationStatus,
    source: str,
    note: str | None = None,
    interview_round: int | None = None,
) -> Application:
    """裁决并执行状态推进；拒绝时落 rejected history 后抛 409。"""

    current = ApplicationStatus(application.status)
    decision = can_transition(current, target, source)

    if decision.idempotent and current == target:
        _apply_side_fields(application, note, interview_round)
        session.add(application)
        session.commit()
        return application

    if not decision.allowed:
        session.add(
            StatusHistory(
                application_id=application.id,
                from_status=current.value,
                to_status=target.value,
                source=source,
                rejected=True,
            )
        )
        session.commit()
        raise state_conflict(decision.reason, details={"current": current.value, "target": target.value, "source": source})

    application.status = target.value
    if target == ApplicationStatus.submitted and application.applied_at is None:
        from autohunt_domain.models import utcnow

        application.applied_at = utcnow()
    _apply_side_fields(application, note, interview_round)
    session.add(application)
    session.add(
        StatusHistory(
            application_id=application.id,
            from_status=current.value,
            to_status=target.value,
            source=source,
            rejected=False,
        )
    )
    session.commit()
    session.refresh(application)
    return application


def _apply_side_fields(application: Application, note: str | None, interview_round: int | None) -> None:
    if note is not None:
        application.note = note
    if interview_round is not None:
        application.interview_round = interview_round
