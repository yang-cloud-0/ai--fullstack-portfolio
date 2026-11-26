from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def analyze(question):
    response = client.post("/analyze", json={"question": question})
    assert response.status_code == 200
    return response.json()


def test_distinguishes_paid_orders_from_total_orders():
    paid = analyze("2026年11月华东的成交单量是多少")
    total = analyze("2026-11 华东 订单总数是多少")
    assert (paid["metric"], total["metric"]) == ("paid_orders", "order_count")
    assert paid["month"] == "2026-11"
    assert paid["region"] == "华东"


def test_ambiguous_metric_and_multiple_months_need_clarification():
    result = analyze("2026-10 到 2026-11 华东订单数怎么样")
    assert result["status"] == "clarify"
    assert result["metric"] is None
    assert "一个明确的年月" in result["reason"]


def test_multiple_metrics_and_unsupported_region_need_clarification():
    result = analyze("2026-11 广东的净销售额和退款额")
    assert result["status"] == "clarify"
    assert "一个指标" in result["reason"]
    assert "一个区域" in result["reason"]


def test_model_timeout_falls_back_to_catalog_definition():
    with (
        patch.object(main, "MODEL_ENDPOINT", "https://model.invalid/v1/chat/completions"),
        patch.object(main.httpx, "post", side_effect=httpx.ReadTimeout("模拟超时")),
    ):
        result = analyze("2026-11 全国净销售额")
    assert result["status"] == "ready"
    assert result["metric"] == "net_revenue"
    assert "采用指标目录口径" in result["reason"]


def test_model_explanation_cannot_change_query_fields():
    with (
        patch.object(main, "MODEL_ENDPOINT", "https://model.invalid/v1/chat/completions"),
        patch.object(main, "reason_with_model", return_value="模型输出的说明"),
    ):
        result = analyze("2026-11 华东退款额")
    assert result["reason"] == "模型输出的说明"
    assert (result["metric"], result["region"]) == ("refund_amount", "华东")


def test_invalid_request_is_rejected():
    assert client.post("/analyze", json={"question": ""}).status_code == 422
