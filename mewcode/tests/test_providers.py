import asyncio
import json

import httpx
import pytest

from mewcode.providers import Conversation, ProviderConfig, ProviderError, SSEProvider


class Fragments(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        # 每 3 个字节切一次，也会切开 UTF-8 汉字和 SSE 的换行。
        for offset in range(0, len(self.body), 3):
            yield self.body[offset:offset + 3]


def stream_body(*events):
    return "".join(
        "data: " + (event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)) + "\r\n\r\n"
        for event in events
    ).encode()


def run_stream(protocol, body, *, status=200, content_type="text/event-stream", fail=None):
    async def run():
        def handler(request):
            assert json.loads(request.content)["stream"] is True
            if protocol == "anthropic":
                assert request.headers["anthropic-version"] == "2023-06-01"
            return httpx.Response(status, headers={"content-type": content_type}, stream=Fragments(body))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            conversation = Conversation(SSEProvider(ProviderConfig(protocol, "https://test.invalid", "mock"), client))
            pieces = []
            if fail:
                with pytest.raises(ProviderError, match=fail):
                    async for delta in conversation.ask("问题"):
                        pieces.append(delta)
                assert conversation.history == []
            else:
                async for delta in conversation.ask("问题"):
                    pieces.append(delta)
                assert conversation.history[-1]["content"] == "".join(pieces)
            return pieces

    return asyncio.run(run())


def test_openai_only_yields_visible_content_across_byte_boundaries():
    body = stream_body(
        {"choices": [{"delta": {"reasoning_content": "隐藏内容"}}]},
        {"choices": [{"delta": {"content": "你"}}]},
        {"choices": [{"delta": {"content": "好"}}]},
        "[DONE]",
    )
    assert run_stream("openai", body) == ["你", "好"]


def test_anthropic_uses_text_deltas_and_ignores_thinking():
    body = stream_body(
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "隐藏内容"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "你好"}},
        {"type": "message_stop"},
    )
    assert run_stream("anthropic", body) == ["你好"]


@pytest.mark.parametrize(
    ("status", "message"), [(401, "鉴权失败"), (403, "鉴权失败"), (404, "不存在"), (429, "额度受限"), (503, "服务暂不可用")]
)
def test_categorizes_http_errors(status, message):
    run_stream("openai", b"", status=status, fail=message)


def test_incomplete_stream_does_not_commit_partial_reply():
    body = stream_body({"choices": [{"delta": {"content": "半截正文"}}]})
    assert run_stream("openai", body, fail="回复未完成") == ["半截正文"]


def test_malformed_json_reports_protocol_error():
    run_stream("openai", stream_body('{"half":'), fail="无法解析")


def test_non_streaming_response_is_detected():
    run_stream("openai", b"{}", content_type="application/json", fail="不是 SSE")


def test_anthropic_stream_error_is_detected():
    body = stream_body({"type": "error", "error": {"type": "overloaded_error"}})
    run_stream("anthropic", body, fail="流式响应中报告错误")
