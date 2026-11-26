import asyncio

import httpx
from textual.widgets import Input

from mewcode.demo import demo_transport
from mewcode.providers import Conversation, ProviderConfig, SSEProvider
from mewcode.tui import ChatApp


def test_tui_submits_question_and_clears_history():
    async def run():
        async with httpx.AsyncClient(transport=demo_transport("anthropic")) as client:
            conversation = Conversation(
                SSEProvider(ProviderConfig("anthropic", "http://localhost/demo", "fixture"), client)
            )
            app = ChatApp(conversation)
            async with app.run_test() as pilot:
                app.query_one(Input).value = "你好"
                await pilot.press("enter")
                await app.workers.wait_for_complete()
                assert len(conversation.history) == 2
                assert "已接收「你好」" in conversation.history[-1]["content"]
                await pilot.press("ctrl+l")
                assert conversation.history == []

    asyncio.run(run())
