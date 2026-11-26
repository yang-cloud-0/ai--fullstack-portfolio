"""把电商问题收敛为 Java 服务可以校验的结构化查询计划。"""

import json
import os
import re
from pathlib import Path
from typing import Literal, TypedDict

import httpx
from fastapi import FastAPI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

CATALOG_PATH = Path(
    os.environ.get("CATALOG_PATH", Path(__file__).resolve().parents[1] / "catalog" / "metrics.json")
)
CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
MONTH_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*[-年]\s*(0?[1-9]|1[0-2])(?!\d)\s*月?")
MODEL_ENDPOINT = os.environ.get("MODEL_CHAT_COMPLETIONS_URL", "")


class Request(BaseModel):
    question: str = Field(min_length=1, max_length=400)


class Plan(BaseModel):
    status: Literal["ready", "clarify", "unavailable"]
    metric: str | None = None
    month: str | None = None
    region: str | None = None
    reason: str
    version: str


class State(TypedDict, total=False):
    question: str
    candidates: list[dict]
    months: list[str]
    regions: list[str]
    plan: Plan


def retrieve(state: State) -> dict:
    """召回目录条目并独立提取确定性筛选条件。"""
    question = state["question"]
    matched = []
    for metric in CATALOG["metrics"]:
        length = max((len(alias) for alias in metric["aliases"] if alias in question), default=0)
        if length:
            matched.append((length, metric))
    matched.sort(key=lambda item: -item[0])
    # 「已支付订单」属于「支付订单」的一种写法，按指标去重。
    candidates = [metric for _, metric in matched]
    months = sorted({f"{year}-{int(month):02d}" for year, month in MONTH_PATTERN.findall(question)})
    regions = [region for region in CATALOG["regions"] if region in question]
    return {"candidates": candidates, "months": months, "regions": regions}


def reason_with_model(question: str, metric: dict) -> str:
    """模型解释已确认的业务口径，查询指标与过滤条件由程序确定。"""
    response = httpx.post(
        MODEL_ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ.get('MODEL_API_KEY', '')}"},
        json={
            "model": os.environ.get("MODEL_NAME", ""),
            "max_tokens": 160,
            "messages": [
                {
                    "role": "system",
                    "content": "用一句中文解释给定的指标口径。不要输出查询语句或查询结果。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": question, "metric": metric["name"], "definition": metric["definition"]},
                        ensure_ascii=False,
                    ),
                },
            ],
        },
        timeout=httpx.Timeout(4.0),
        follow_redirects=False,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("模型未返回有效的口径说明")
    return content.strip()[:300]


def prepare_plan(state: State) -> dict:
    options = state["candidates"]
    issues = []
    if len(options) != 1:
        issues.append("请指定一个指标（订单总数、支付订单数、净销售额或退款总额）")
    if len(state["months"]) != 1:
        issues.append("请提供一个明确的年月，例如 2026-11")
    if len(state["regions"]) != 1:
        issues.append("请指定一个区域（华东、华北、华南或全国）")

    base = {"version": CATALOG["version"]}
    if issues:
        return {"plan": Plan(status="clarify", reason="；".join(issues), **base)}

    metric = options[0]
    reason = metric["definition"]
    if MODEL_ENDPOINT:
        try:
            reason = reason_with_model(state["question"], metric)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            reason = f"模型说明暂不可用，采用指标目录口径：{metric['definition']}"
    return {
        "plan": Plan(
            status="ready",
            metric=metric["id"],
            month=state["months"][0],
            region=state["regions"][0],
            reason=reason,
            **base,
        )
    }


workflow = StateGraph(State)
workflow.add_node("retrieve", retrieve)
workflow.add_node("prepare_plan", prepare_plan)
workflow.add_edge(START, "retrieve")
workflow.add_edge("retrieve", "prepare_plan")
workflow.add_edge("prepare_plan", END)
graph = workflow.compile()
app = FastAPI(title="经营指标查询计划")


@app.get("/health")
def health() -> dict:
    return {"status": "up"}


@app.post("/analyze", response_model=Plan)
def analyze(request: Request) -> Plan:
    return graph.invoke({"question": request.question}, config={"recursion_limit": 5})["plan"]
