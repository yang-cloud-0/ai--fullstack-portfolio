"""回放两种协议的演示事件，无需网络或账号。"""

import json
from collections.abc import AsyncIterator

import httpx


class DemoStream(httpx.AsyncByteStream):
    def __init__(self, events: list):
        self.events = events

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for event in self.events:
            body = event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)
            yield f"data: {body}\n\n".encode()


def demo_transport(protocol: str) -> httpx.MockTransport:
    def response(request: httpx.Request) -> httpx.Response:
        question = json.loads(request.content)["messages"][-1]["content"]
        reply = ["你好，", f"已接收「{question[:80]}」。", "这条回复来自本地协议回放。"]
        if protocol == "openai":
            events = [{"choices": [{"delta": {"content": text}}]} for text in reply]
            events.append("[DONE]")
        else:
            events = [
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}
                for text in reply
            ]
            events.append({"type": "message_stop"})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=DemoStream(events))

    return httpx.MockTransport(response)
