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
    assert "采用指标目录口径" in result["model_note"]


def test_model_explanation_cannot_change_query_fields():
    with (
        patch.object(main, "MODEL_ENDPOINT", "https://model.invalid/v1/chat/completions"),
        patch.object(main, "reason_with_model", return_value="模型输出的说明"),
    ):
        result = analyze("2026-11 华东退款额")
    assert result["model_note"] == "模型输出的说明"
    assert result["reason"] == "已支付订单的退款金额总和"
    assert (result["metric"], result["region"]) == ("refund_amount", "华东")


def test_invalid_request_is_rejected():
    assert client.post("/analyze", json={"question": ""}).status_code == 422


def test_model_tool_can_suggest_but_cannot_skip_human_confirmation():
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://model.invalid"),
        json={"choices": [{"message": {"tool_calls": [{"function": {
            "name": "suggest_metric", "arguments": '{"metric":"paid_orders"}',
        }}]}}]},
    )
    with (
        patch.object(main, "MODEL_ENDPOINT", "https://model.invalid"),
        patch.object(main.httpx, "post", return_value=response) as post,
    ):
        result = analyze("2026-11 华东付了款的有几笔")
    assert post.call_args.kwargs["json"]["tool_choice"]["function"]["name"] == "suggest_metric"
    assert "模型建议「支付订单数」" in result["reason"]
    assert result["status"] == "clarify" and result["metric"] is None


def test_broken_model_tool_json_returns_deterministic_clarification():
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://model.invalid"),
        json={"choices": [{"message": {"tool_calls": [{"function": {
            "name": "suggest_metric", "arguments": '{"metric":',
        }}]}}]},
    )
    with (
        patch.object(main, "MODEL_ENDPOINT", "https://model.invalid"),
        patch.object(main.httpx, "post", return_value=response) as post,
    ):
        result = analyze("2026-11 华东付了款的有几笔")
    assert post.call_count == 1
    assert result["status"] == "clarify" and "模型建议" not in result["reason"]
