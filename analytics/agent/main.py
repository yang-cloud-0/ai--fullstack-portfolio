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
    model_note: str | None = None


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


def model_message(system: str, data: dict, tool: dict | None = None) -> dict:
    body = {
        "model": os.environ.get("MODEL_NAME", ""),
        "max_tokens": 160,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
    }
    if tool:
        body["tools"] = [tool]
        body["tool_choice"] = {"type": "function", "function": {"name": tool["function"]["name"]}}
    response = httpx.post(
        MODEL_ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ.get('MODEL_API_KEY', '')}"},
        json=body,
        timeout=httpx.Timeout(4.0),
        follow_redirects=False,
    )
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]
    if not isinstance(message, dict):
        raise ValueError("模型消息格式无效")
    return message


def reason_with_model(question: str, metric: dict) -> str:
    """模型解释已确认的业务口径，查询指标与过滤条件由程序确定。"""
    message = model_message(
        "用一句中文解释给定的指标口径。不要输出查询语句或查询结果。",
        {"question": question, "metric": metric["name"], "definition": metric["definition"]},
    )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("模型未返回有效的口径说明")
    return content.strip()[:300]


def suggest_metric(question: str) -> str | None:
    """工具仅返回供用户确认的建议，不执行数据库查询。"""
    metrics = {metric["id"]: metric["name"] for metric in CATALOG["metrics"]}
    tool = {
        "type": "function",
        "function": {
            "name": "suggest_metric",
            "description": "建议一个目录内的业务指标，无法判断时返回 unknown",
            "parameters": {
                "type": "object",
                "properties": {"metric": {"type": "string", "enum": [*metrics, "unknown"]}},
                "required": ["metric"],
                "additionalProperties": False,
            },
        },
    }
    message = model_message("从给定目录建议一个指标，避免猜测。", {"question": question, "catalog": metrics}, tool)
    calls = message["tool_calls"]
    if len(calls) != 1 or calls[0]["function"]["name"] != "suggest_metric":
        raise ValueError("模型返回了不受支持的工具")
    arguments = json.loads(calls[0]["function"]["arguments"])
    if not isinstance(arguments, dict) or set(arguments) != {"metric"}:
        raise ValueError("工具参数格式不正确")
    selected = arguments["metric"]
    return metrics.get(selected) if isinstance(selected, str) else None



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
        if MODEL_ENDPOINT and not options and len(state["months"]) == len(state["regions"]) == 1:
            try:
                suggestion = suggest_metric(state["question"])
                if suggestion:
                    issues.append(f"模型建议「{suggestion}」，请在问题中明确指标")
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                pass  # 保留确定性的澄清提示，避免失败后重复调用模型。
        return {"plan": Plan(status="clarify", reason="；".join(issues), **base)}

    metric = options[0]
    model_note = None
    if MODEL_ENDPOINT:
        try:
            model_note = reason_with_model(state["question"], metric)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            model_note = "模型说明暂不可用，采用指标目录口径。"
    return {
        "plan": Plan(
            status="ready",
            metric=metric["id"],
            month=state["months"][0],
            region=state["regions"][0],
            reason=metric["definition"],
            model_note=model_note,
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
