"""确认流闭环（FR-22/23/24 + BR-1，§3.4）—— 覆盖 AC-2 / AC-3 负例矩阵 / AC-4（B-2 闭环）。"""

from tests.conftest import make_application, make_confirmation


def _confirmed(client, ui, agent, request_id="req-1"):
    """建岗 → 建投递 → Agent 建确认单 → UI 确认（改值），返回 (app_id, confirmation_id, confirm_body)。"""

    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id, request_id=request_id)
    confirmed = client.post(
        f"/api/v1/confirmations/{confirmation_id}/confirm",
        json={"confirmed_fields": {"姓名": "张三", "电话": "13911111111"}},  # 用户改电话
        **ui,
    )
    assert confirmed.status_code == 200, confirmed.text
    return app_id, confirmation_id, confirmed.json()


# ---------- AC-2 端到端主链路 ----------


def test_ac2_end_to_end_user_edit_roundtrip(client, ui, agent):
    """AC-2：用户改值 → Agent 读回修改后值 + submit_token。"""

    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)

    created = client.post(
        "/api/v1/confirmations",
        json={"application_id": app_id, "request_id": "req-1",
              "fields": {"姓名": "张三", "电话": "13800000000"}},
        **agent,
    )
    # 同 request_id 重试幂等（见 test_idempotent_retry）
    assert created.status_code == 200

    pending = client.get(f"/api/v1/confirmations/{confirmation_id}", **agent)
    assert pending.status_code == 200
    assert pending.json() == {"status": "待确认"}  # 无其他字段，无任何许可

    confirmed = client.post(
        f"/api/v1/confirmations/{confirmation_id}/confirm",
        json={"confirmed_fields": {"姓名": "张三", "电话": "13911111111"}},
        **ui,
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["confirmed_fields"]["电话"] == "13911111111"
    assert body["submit_token"].startswith("ah_submit_")
    assert body["expires_at"]

    polled = client.get(f"/api/v1/confirmations/{confirmation_id}", **agent)
    assert polled.json()["confirmed_fields"]["电话"] == "13911111111"  # Agent 读回修改后值
    assert polled.json()["submit_token"] == body["submit_token"]


# ---------- AC-3 负例矩阵 ----------


def test_ac3_create_response_carries_no_permit(client, agent):
    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)
    resp = client.post(
        "/api/v1/confirmations",
        json={"application_id": app_id, "request_id": "req-2", "fields": {"a": "b"}},
        **agent,
    )
    assert resp.status_code == 201
    assert set(resp.json().keys()) == {"confirmation_id", "status"}  # 响应不携带任何可提交许可
    _ = confirmation_id


def test_ac3_idempotent_retry_same_request_id(client, agent):
    """AC-3 异常重试：同 request_id 返回首个确认单（首次 201、命中 200）。"""

    _, app_id = make_application(client, agent)
    first = client.post(
        "/api/v1/confirmations",
        json={"application_id": app_id, "request_id": "req-dup", "fields": {"a": "b"}},
        **agent,
    )
    assert first.status_code == 201
    retry = client.post(
        "/api/v1/confirmations",
        json={"application_id": app_id, "request_id": "req-dup", "fields": {"a": "b"}},
        **agent,
    )
    assert retry.status_code == 200
    assert retry.json()["confirmation_id"] == first.json()["confirmation_id"]


def test_ac3_agent_direct_confirm_reject_reissue_403(client, ui, agent):
    """BR-1 最后一道门：Agent Bearer 直调 confirm/reject/reissue 一律 403。"""

    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)
    for endpoint in ("confirm", "reject", "reissue"):
        resp = client.post(
            f"/api/v1/confirmations/{confirmation_id}/{endpoint}",
            json={"confirmed_fields": {}, "reason": "x"},
            **agent,
        )
        assert resp.status_code == 403, endpoint
        assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_ac3_submit_result_permit_matrix(client, ui, agent):
    """无 token → PERMIT_REQUIRED；伪造/跨确认单 → PERMIT_INVALID。"""

    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)
    token = confirmed["submit_token"]

    no_token = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": "", "result": "success", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert no_token.status_code == 403
    assert no_token.json()["error"]["code"] == "PERMIT_REQUIRED"

    bogus = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": "ah_submit_forged", "result": "success",
              "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert bogus.status_code == 403
    assert bogus.json()["error"]["code"] == "PERMIT_INVALID"

    # 跨确认单：B 的 token 用于 A 的投递
    _, app_id_b = make_application(client, agent, company="腾讯", title="产品")
    confirmation_b = make_confirmation(client, agent, app_id_b, request_id="req-b")
    client.post(
        f"/api/v1/confirmations/{confirmation_b}/confirm",
        json={"confirmed_fields": {"姓名": "李四"}},
        **ui,
    )
    cross = client.post(
        f"/api/v1/applications/{app_id_b}/submit-result",
        json={"submit_token": token, "result": "success", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert cross.status_code == 403
    assert cross.json()["error"]["code"] == "PERMIT_INVALID"


def test_ac3_agent_patch_submitted_requires_permit(client, ui, agent):
    """AC-3：Agent 直调 PATCH 推「已投递」无 token 被拒（反绕过路径）。"""

    _, app_id = make_application(client, agent)
    resp = client.patch(f"/api/v1/applications/{app_id}", json={"status": "已投递"}, **agent)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMIT_REQUIRED"

    forged = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "已投递", "submit_token": "ah_submit_forged"},
        **agent,
    )
    assert forged.status_code == 403
    assert forged.json()["error"]["code"] == "PERMIT_INVALID"

    # UI 手动推进不受限（用户本人即确认者）
    ok = client.patch(f"/api/v1/applications/{app_id}", json={"status": "已投递"}, **ui)
    assert ok.status_code == 200


def test_ac3_agent_patch_submitted_with_permit_via_header(client, ui, agent):
    """§3.4 步骤 4：Permit 头携带 token 可推进「已投递」，且 token 被一次性消耗。"""

    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)
    token = confirmed["submit_token"]

    ok = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "已投递"},
        headers={"Authorization": agent["headers"]["Authorization"], "Permit": token},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "已投递"

    reuse = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "笔试"},  # 已投递 → 笔试本属合法前进，但消耗后的 token 不能再用于别处
        **agent,
    )
    assert reuse.status_code == 200
    submit = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": token, "result": "success", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert submit.status_code == 403
    assert submit.json()["error"]["code"] == "PERMIT_INVALID"  # 已消耗


def test_ac3_ui_cannot_call_submit_result(client, ui, agent):
    """BR-1 双向封堵：UI 凭证调 submit-result 亦 403（端点仅 AgentBearer）。"""

    app_id, _, _ = _confirmed(client, ui, agent)
    resp = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": "x", "result": "success", "submitted_at": "2026-08-25T14:00:00"},
        **ui,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


# ---------- AC-4 回写与 B-2 闭环 ----------


def test_ac4_submit_success(client, ui, agent):
    app_id, _, confirmed = _confirmed(client, ui, agent)
    resp = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "success",
              "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已投递"
    assert resp.json()["recorded"] is True

    listed = client.get("/api/v1/applications", **ui).json()["items"][0]
    assert listed["status"] == "已投递"
    assert listed["applied_at"] is not None


def test_ac4_submit_failed_keeps_snapshot(client, ui, agent):
    """FR-24：失败回写记录 fail_reason、保留字段快照、状态留待人工处置；token 仍被消耗。"""

    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)
    missing_reason = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "failed",
              "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert missing_reason.status_code == 422  # failed 缺 fail_reason

    resp = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "failed",
              "fail_reason": "目标站点验证码拦截", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "待投递"  # 状态不变，留待用户人工处置

    detail = client.get(f"/api/v1/confirmations/{confirmation_id}", **ui).json()
    assert detail["status"] == "已确认"
    assert detail["confirmed_fields"]["电话"] == "13911111111"  # 快照保留
    assert detail["submit_token"] is None  # 已消耗


def test_ac4_reissue_closed_loop(client, ui, agent):
    """B-2 闭环：过期 → 回写 403 → 查询无 token → UI 重新放行 → 新 token 回写成功。"""

    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)
    old_token = confirmed["submit_token"]

    # 测试钩子：强制过期（TTL 亦可经 AUTOHUNT_SUBMIT_TOKEN_TTL_SECONDS 调小）
    expired = client.post(f"/__test__/confirmations/{confirmation_id}/force-expire")
    assert expired.status_code == 200

    denied = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": old_token, "result": "success", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMIT_INVALID"

    polled = client.get(f"/api/v1/confirmations/{confirmation_id}", **agent).json()
    assert polled["status"] == "已确认"
    assert polled["submit_token"] is None  # 过期即不再下发

    reissued = client.post(f"/api/v1/confirmations/{confirmation_id}/reissue", **ui)
    assert reissued.status_code == 200
    new_token = reissued.json()["submit_token"]
    assert new_token != old_token
    assert reissued.json()["confirmed_fields"] == confirmed["confirmed_fields"]  # 字段不变

    ok = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": new_token, "result": "success", "submitted_at": "2026-08-25T14:05:00"},
        **agent,
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "已投递"

    # 已回写成功不可重新放行
    again = client.post(f"/api/v1/confirmations/{confirmation_id}/reissue", **ui)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "STATE_CONFLICT"


def test_reissue_preconditions_409(client, ui, agent):
    """reissue 前提：非已确认态 409；token 仍有效 409。"""

    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)
    not_confirmed = client.post(f"/api/v1/confirmations/{confirmation_id}/reissue", **ui)
    assert not_confirmed.status_code == 409

    client.post(
        f"/api/v1/confirmations/{confirmation_id}/confirm",
        json={"confirmed_fields": {"姓名": "张三"}},
        **ui,
    )
    still_valid = client.post(f"/api/v1/confirmations/{confirmation_id}/reissue", **ui)
    assert still_valid.status_code == 409


def test_ac4_failed_consumes_token_then_reissue_allowed(client, ui, agent):
    """TC-SUB-06：失败回写消耗 token 后仍可重新放行。"""

    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)
    client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "failed",
              "fail_reason": "站点超时", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    reissued = client.post(f"/api/v1/confirmations/{confirmation_id}/reissue", **ui)
    assert reissued.status_code == 200


def test_hash_binding_tamper_hook(client, ui, agent):
    """测试钩子②：篡改 confirmed_fields → 绑定哈希失配 → PERMIT_INVALID。"""

    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)
    tampered = client.post(
        f"/__test__/confirmations/{confirmation_id}/tamper-fields",
        json={"fields": {"姓名": "张三", "电话": "110"}},
    )
    assert tampered.status_code == 200
    resp = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "success",
              "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMIT_INVALID"


def test_reject_flow(client, ui, agent):
    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)
    rejected = client.post(
        f"/api/v1/confirmations/{confirmation_id}/reject", json={"reason": "岗位不匹配"}, **ui
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "已驳回"
    assert rejected.json()["reason"] == "岗位不匹配"

    polled = client.get(f"/api/v1/confirmations/{confirmation_id}", **agent).json()
    assert polled["status"] == "已驳回"
    assert "submit_token" not in polled


# ---------- 契约 v2 修订：列表 / UI 快照变体 / 手动关闭 / 回写字段 ----------


def test_list_confirmations_ui_only(client, ui, agent):
    """GET /confirmations：仅 UI；返回摘要（不含 fields 快照）。"""
    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)

    denied = client.get("/api/v1/confirmations", **agent)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    listed = client.get("/api/v1/confirmations", **ui)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [i["id"] for i in items] == [confirmation_id]
    assert items[0]["status"] == "待确认"
    assert "fields" not in items[0]  # 摘要不带快照，快照走 GET /{id} UI 变体

    filtered = client.get("/api/v1/confirmations?status=已确认", **ui)
    assert filtered.json()["items"] == []


def test_pending_snapshot_ui_vs_agent(client, ui, agent):
    """待确认变体按 caller 区分：UI 见快照，Agent 仅 {status}（BR-1 不变）。"""
    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)

    as_agent = client.get(f"/api/v1/confirmations/{confirmation_id}", **agent)
    assert as_agent.json() == {"status": "待确认"}

    as_ui = client.get(f"/api/v1/confirmations/{confirmation_id}", **ui)
    body = as_ui.json()
    assert body["status"] == "待确认"
    assert body["fields"] == {"姓名": "张三", "电话": "13800000000"}
    assert body["application_id"] == app_id
    assert "submit_token" not in body  # 快照不含任何许可


def test_close_pending_flow(client, ui, agent):
    """手动关闭：待确认 → 已超时关闭；非待确认 409；Agent 403。"""
    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)

    denied = client.post(f"/api/v1/confirmations/{confirmation_id}/close", json={}, **agent)
    assert denied.status_code == 403

    closed = client.post(
        f"/api/v1/confirmations/{confirmation_id}/close", json={"reason": "岗位已下架"}, **ui
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "已超时关闭"
    assert closed.json()["reason"] == "岗位已下架"

    polled = client.get(f"/api/v1/confirmations/{confirmation_id}", **agent).json()
    assert polled["status"] == "已超时关闭"

    again = client.post(f"/api/v1/confirmations/{confirmation_id}/close", json={}, **ui)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "STATE_CONFLICT"


def test_close_confirmed_rejected(client, ui, agent):
    """已确认不可手动关闭（走重新放行/回写闭环）。"""
    _, confirmation_id, _ = _confirmed(client, ui, agent)
    resp = client.post(f"/api/v1/confirmations/{confirmation_id}/close", json={}, **ui)
    assert resp.status_code == 409


def test_confirmed_detail_carries_submit_result(client, ui, agent):
    """FR-24 结果视图：回写后 GET 已确认响应含 submit_result/fail_reason/submitted_at。"""
    app_id, confirmation_id, confirmed = _confirmed(client, ui, agent)

    before = client.get(f"/api/v1/confirmations/{confirmation_id}", **ui).json()
    assert before["submit_result"] is None
    assert before["fail_reason"] is None

    client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "failed",
              "fail_reason": "目标站点验证码拦截", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    after = client.get(f"/api/v1/confirmations/{confirmation_id}", **ui).json()
    assert after["submit_result"] == "failed"
    assert after["fail_reason"] == "目标站点验证码拦截"
    assert after["submitted_at"] is not None


# ---------- G3 复核：列表分页加固 / D7 / D8 / D9 ----------


def test_list_confirmations_bad_cursor_limit_422(client, ui):
    resp = client.get("/api/v1/confirmations?cursor=abc", **ui)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    for bad in ("0", "-1"):
        resp = client.get(f"/api/v1/confirmations?limit={bad}", **ui)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_result_missing_token_403(client, ui, agent):
    """D7：submit_token 缺失（schema 非必填）→ 403 PERMIT_REQUIRED（契约语义，非 422）。"""
    app_id, _, _ = _confirmed(client, ui, agent)
    resp = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"result": "success", "submitted_at": "2026-08-25T14:00:00"},
        **agent,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMIT_REQUIRED"


def test_submit_result_date_only_submitted_at_422(client, ui, agent):
    """D8：submitted_at 拒绝 date-only，须为完整 RFC3339（FastAPI 默认 422）。"""
    app_id, _, confirmed = _confirmed(client, ui, agent)
    resp = client.post(
        f"/api/v1/applications/{app_id}/submit-result",
        json={"submit_token": confirmed["submit_token"], "result": "success",
              "submitted_at": "2026-08-25"},
        **agent,
    )
    assert resp.status_code == 422


def test_confirmed_carries_confirmed_at(client, ui, agent):
    """D9：ConfirmationConfirmed 响应（confirm 直返 + GET 轮询）均含 confirmed_at。"""
    _, confirmation_id, confirmed = _confirmed(client, ui, agent)
    assert "confirmed_at" in confirmed
    assert confirmed["confirmed_at"] is not None

    polled = client.get(f"/api/v1/confirmations/{confirmation_id}", **ui).json()
    assert polled["status"] == "已确认"
    assert polled["confirmed_at"] == confirmed["confirmed_at"]
