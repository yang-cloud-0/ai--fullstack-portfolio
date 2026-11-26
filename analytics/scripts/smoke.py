"""使用运行中的 HTTP 接口验证实际结果与 SSE 续传。"""

import argparse
import json
import uuid

import httpx


def create(client, question, key=None):
    token = key or str(uuid.uuid4())
    response = client.post("/api/runs", json={"question": question}, headers={"Idempotency-Key": token})
    assert response.status_code == 202, response.text
    return response.json()["id"], token


def subscribe(client, run_id, after=0):
    headers = {"Last-Event-ID": str(after)} if after else {}
    with client.stream("GET", f"/api/runs/{run_id}/events", headers=headers) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["x-accel-buffering"] == "no"
        event_id = None
        events = []
        for line in response.iter_lines():
            if line.startswith("id:"):
                event_id = int(line.split(":", 1)[1])
            elif line.startswith("data:"):
                assert event_id is not None
                events.append((event_id, json.loads(line[5:])))
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--expect-redis", action="store_true")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        question = "2026-11 华东成交单量是多少？"
        paid_id, key = create(client, question)
        assert create(client, question, key)[0] == paid_id
        conflict = client.post("/api/runs", json={"question": "不同问题"}, headers={"Idempotency-Key": key})
        assert conflict.status_code == 409

        paid_events = subscribe(client, paid_id)
        assert [seq for seq, _ in paid_events] == [1, 2, 3]
        assert [payload["status"] for _, payload in paid_events] == ["QUEUED", "RUNNING", "SUCCEEDED"]
        assert subscribe(client, paid_id, after=2) == [paid_events[-1]]
        done = client.get(f"/api/runs/{paid_id}/events", headers={"Last-Event-ID": "3"})
        assert done.status_code == 204
        assert client.get(f"/api/runs/{paid_id}").json() == paid_events[-1][1]
        paid = paid_events[-1][1]["result"]
        assert paid["value"] == 3 and paid["metric"] == "paid_orders"

        total_id, _ = create(client, "2026-11 华东订单总数")
        total = subscribe(client, total_id)[-1][1]["result"]
        assert total["value"] == 5 and total["metric"] == "order_count"

        ambiguous_id, _ = create(client, "华东 订单怎么样")
        assert subscribe(client, ambiguous_id)[-1][1]["status"] == "CLARIFY"
        print("口径对照：支付订单 3 笔，全部订单 5 笔；歧义问题要求补充条件。")
        print("同一幂等键复用任务；改请求体返回 409；事件 2 之后仅回放 1 条终态。")

        if args.expect_redis:
            next_id, _ = create(client, question)
            cached = subscribe(client, next_id)[-1][1]["result"]
            assert cached["source"] == "cache" and cached["value"] == 3
            print(f"Redis 路径：支付订单首次来源 {paid['source']}，再次来源 {cached['source']}。")


if __name__ == "__main__":
    main()
