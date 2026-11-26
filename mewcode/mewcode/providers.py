"""把两种模型协议转换为可消费的异步文本流。"""

import json
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

import httpx


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ProviderConfig:
    protocol: Literal["openai", "anthropic"]
    endpoint: str
    model: str
    api_key_env: str = ""


class Provider(Protocol):
    def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]: ...


class ProviderError(Exception):
    pass


async def sse_data(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    fields = []
    async for line in lines:
        if not line:
            if fields:
                yield "\n".join(fields)
                fields.clear()
        elif line.startswith("data:"):
            value = line[5:]
            fields.append(value.removeprefix(" "))


def http_failure(status: int) -> ProviderError:
    if status in (401, 403):
        return ProviderError(f"鉴权失败（HTTP {status}），请检查密钥和模型权限")
    if status == 429:
        return ProviderError("调用频率或额度受限（HTTP 429），请稍后手动重试")
    if status == 404:
        return ProviderError("端点或模型不存在（HTTP 404），请检查配置")
    if status >= 500:
        return ProviderError(f"模型服务暂不可用（HTTP {status}）")
    return ProviderError(f"模型请求失败（HTTP {status}）")


class SSEProvider:
    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient):
        self.config = config
        self.client = client

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        config = self.config
        url = httpx.URL(config.endpoint)
        if url.username or url.password or not (
            url.scheme == "https"
            or url.scheme == "http" and url.host in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ProviderError("远程模型端点应使用 HTTPS，本地测试可使用环回 HTTP")
        key = os.getenv(config.api_key_env, "") if config.api_key_env else ""
        if config.api_key_env and not key:
            raise ProviderError(f"缺少环境变量 {config.api_key_env}")
        headers = {"Accept": "text/event-stream"}
        payload = {"model": config.model, "stream": True, "messages": list(messages)}
        if config.protocol == "anthropic":
            headers.update({"anthropic-version": "2023-06-01", "x-api-key": key})
            payload["max_tokens"] = 2048
        elif key:
            headers["Authorization"] = f"Bearer {key}"

        try:
            async with self.client.stream(
                "POST", url, headers=headers, json=payload, follow_redirects=False
            ) as response:
                if response.status_code != 200:
                    raise http_failure(response.status_code)
                if "text/event-stream" not in response.headers.get("content-type", "").lower():
                    raise ProviderError("模型返回的内容不是 SSE 事件流")
                async for data in sse_data(response.aiter_lines()):
                    if config.protocol == "openai" and data == "[DONE]":
                        return
                    event = json.loads(data)
                    if not isinstance(event, dict):
                        raise ProviderError("模型事件格式无效")
                    if "error" in event or event.get("type") == "error":
                        raise ProviderError("模型在流式响应中报告错误")
                    if config.protocol == "anthropic" and event.get("type") == "message_stop":
                        return
                    text = self.extract_text(event)
                    if isinstance(text, str) and text:
                        yield text
        except httpx.TimeoutException as exc:
            raise ProviderError("模型响应超时，请手动重试") from exc
        except httpx.RequestError as exc:
            raise ProviderError("模型网络连接失败") from exc
        except (ValueError, AttributeError, IndexError, TypeError) as exc:
            raise ProviderError("无法解析模型的流式事件") from exc
        raise ProviderError("连接提前结束，回复未完成")

    def extract_text(self, event: dict) -> str | None:
        if self.config.protocol == "anthropic":
            delta = event.get("delta", {})
            if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                return delta.get("text")
            return None
        choices = event.get("choices", [])
        if not choices:
            return None
        return choices[0].get("delta", {}).get("content")


class Conversation:
    """只有收到模型结束事件后，才把用户提问与回答一并记入上下文。"""
    def __init__(self, provider: Provider):
        self.provider = provider
        self.history: list[Message] = []

    def clear(self) -> None:
        self.history.clear()

    async def ask(self, question: str) -> AsyncIterator[str]:
        user: Message = {"role": "user", "content": question}
        parts = []
        length = 0
        async for piece in self.provider.stream([*self.history, user]):
            length += len(piece)
            if length > 32_000:
                raise ProviderError("回复超过本地显示上限")
            parts.append(piece)
            yield piece
        if not parts:
            raise ProviderError("模型未返回可显示的回复")
        self.history.extend([user, {"role": "assistant", "content": "".join(parts)}])
        del self.history[:-24]
