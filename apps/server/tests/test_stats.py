"""统计（FR-50/51/52）+ CSV 导出 —— G3 D3（from/to 非法 → 422）与 D6（Content-Disposition 恢复）。"""

from tests.conftest import make_application


def _assert_validation_error(resp):
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_stats_overview_bad_from_422(client, ui):
    _assert_validation_error(client.get("/api/v1/stats/overview?from=abc", **ui))


def test_stats_funnel_bad_to_422(client, ui):
    _assert_validation_error(client.get("/api/v1/stats/funnel?to=nope", **ui))


def test_stats_export_bad_from_422(client, ui):
    _assert_validation_error(client.get("/api/v1/stats/export?from=abc", **ui))


def test_stats_overview_bad_from_and_to_422(client, ui):
    _assert_validation_error(client.get("/api/v1/stats/overview?from=abc&to=2026-08-01T00:00:00Z", **ui))
    _assert_validation_error(client.get("/api/v1/stats/overview?from=2026-08-01T00:00:00Z&to=abc", **ui))


def test_export_csv_headers_and_bom(client, ui):
    """D6：Content-Disposition 附件头恢复 + UTF-8 BOM + text/csv。"""
    _, app_id = make_application(client, ui)
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "已投递"}, **ui)

    resp = client.get("/api/v1/stats/export", **ui)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == 'attachment; filename="applications-export.csv"'
    assert resp.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    assert "字节跳动" in resp.text
