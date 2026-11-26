import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from .config import load_config
from .demo import demo_transport
from .providers import Conversation, ProviderConfig, ProviderError, SSEProvider
from .tui import ChatApp


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI 兼容与 Anthropic Messages 终端助手")
    parser.add_argument("--demo", choices=("openai", "anthropic"), help="运行本地协议回放")
    parser.add_argument("--config", type=Path, default=Path.home() / ".config" / "mewcode" / "config.toml")
    parser.add_argument("--profile", help="配置文件中的模型名称")
    parser.add_argument("--prompt", help="在命令行发起单轮对话")
    args = parser.parse_args()

    async def run() -> None:
        if args.demo:
            config = ProviderConfig(args.demo, "http://localhost/demo", "local-fixture")
            transport = demo_transport(args.demo)
        else:
            config = load_config(args.config, args.profile)
            transport = None
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(30, connect=3)) as client:
            conversation = Conversation(SSEProvider(config, client))
            if args.prompt is None:
                await ChatApp(conversation).run_async()
            else:
                if not args.prompt.strip() or len(args.prompt) > 6000:
                    raise ValueError("问题须为 1–6000 个字符")
                async for text in conversation.ask(args.prompt):
                    print(text, end="", flush=True)
                print()

    try:
        asyncio.run(run())
    except (OSError, ValueError, ProviderError) as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
