# MewCode 多协议终端助手

统一 OpenAI Chat Completions 兼容接口与 Anthropic Messages 的异步流式响应。终端界面逐段更新正文，支持最近 12 轮上下文和清空会话。模型回复的结束事件到了才写入历史，半截正文保留在当次界面的失败提示里供调试。

在项目目录使用 Python 3.11+：

```sh
python -m pip install -e ".[test]"
mewcode --demo openai
mewcode --demo anthropic --prompt "介绍一下 SSE"
python -m pytest -q
```

配置真实模型时，将 `config.example.toml` 复制为本地文件，换成已开通的模型名称，并在环境中设置相应密钥变量。使用 `mewcode --config 路径 --profile 模型名` 运行。配置文件保存端点与环境变量名，密钥由运行环境注入。项目只从明确指定的路径或用户配置目录读配置。

测试把协议流按三字节切分，覆盖流被截断、JSON 不完整及鉴权、限流错误。默认演示使用本地回放，不产生模型 API 请求。范围为多轮终端对话，项目没有文件修改或命令执行功能。
