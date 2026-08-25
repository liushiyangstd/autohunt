"""状态机单测（BR-10/BR-11，§5）—— can_transition 纯函数覆盖 AC-6 裁决矩阵。"""

import pytest

from app.schemas import ApplicationStatus as S
from app.services.statemachine import can_transition


@pytest.mark.parametrize(
    "current,target",
    [
        (S.pending, S.submitted),
        (S.submitted, S.written_test),
        (S.written_test, S.interview),
        (S.interview, S.offer),
        (S.offer, S.accepted),
        (S.interview, S.failed),  # 旁路终止态
        (S.submitted, S.abandoned),
        (S.submitted, S.expired),
        (S.failed, S.pending),  # 终态重开仅 UI
        (S.accepted, S.pending),
    ],
)
def test_ui_allows_any_legal_transition(current, target):
    assert can_transition(current, target, "ui").allowed


@pytest.mark.parametrize(
    "current,target",
    [
        (S.pending, S.submitted),
        (S.pending, S.interview),  # 跨级前进允许
        (S.submitted, S.written_test),
        (S.interview, S.offer),
        (S.submitted, S.failed),  # agent 白名单：未通过
    ],
)
def test_agent_forward_allowed(current, target):
    assert can_transition(current, target, "agent").allowed


@pytest.mark.parametrize(
    "current,target",
    [
        (S.interview, S.submitted),  # 回退
        (S.offer, S.written_test),
        (S.written_test, S.pending),
        (S.submitted, S.rejected),  # agent 白名单外终态
        (S.submitted, S.abandoned),  # 主动放弃仅 UI
        (S.submitted, S.expired),  # 已过期仅 UI
        (S.submitted, S.accepted),  # 已接受仅 UI
        (S.failed, S.interview),  # 终态之后自动来源一律拒绝
        (S.rejected, S.offer),
    ],
)
def test_agent_rejected_transitions(current, target):
    decision = can_transition(current, target, "agent")
    assert not decision.allowed


def test_email_terminal_whitelist():
    assert can_transition(S.submitted, S.failed, "email").allowed  # 未通过
    assert can_transition(S.interview, S.rejected, "email").allowed  # 拒信
    assert not can_transition(S.submitted, S.abandoned, "email").allowed
    assert not can_transition(S.submitted, S.expired, "email").allowed
    assert not can_transition(S.submitted, S.accepted, "email").allowed


def test_same_state_idempotent_success():
    decision = can_transition(S.interview, S.interview, "agent")
    assert decision.allowed and decision.idempotent
